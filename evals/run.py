"""python -m evals.run --dataset chat_v1 [--subset smoke] [--category X] [--max-cost-usd 3]

Runs every case through the real chat loop, scores it, writes evals/results/<ts>_<dataset>_
<prompt>.json and a Markdown summary (docs/EVAL_RESULTS.md for full runs), and exits non-zero
when a score is below evals/thresholds.yaml. --compare A.json B.json diffs two result files.
"""

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import yaml
from psycopg.types.json import Jsonb

from backend.config import settings
from backend.db import get_connection
from backend.llm.client import chat, system_prompt
from backend.llm.providers import AzureOpenAIProvider
from backend.observability import tracing
from backend.rag import shields
from backend.rag.retrieval import search
from backend.tools import ToolContext
from evals import evaluators as ev
from evals.evaluators import judges
from mcp_server.client import McpTools
from mcp_server.server import build_server

ROOT = Path(__file__).parent
DATASETS = ROOT / "datasets"
RESULTS = ROOT / "results"
THRESHOLDS = ROOT / "thresholds.yaml"
REPORT = ROOT.parent / "docs" / "EVAL_RESULTS.md"
JUDGED = {"groundedness", "guardrail"}


def load_cases(dataset: str, subset: str | None = None, category: str | None = None):
    lines = (DATASETS / f"{dataset}.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    if subset:
        cases = [c for c in cases if subset in c.get("tags", [])]
    if category:
        cases = [c for c in cases if c["category"] == category]
    return cases


def _plain(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def golden_rows(conn, case: dict, now: datetime) -> list[tuple] | None:
    g = case.get("golden") or {}
    if "sql" not in g:
        return None
    rows = conn.execute(g["sql"], {**g.get("params", {}), "now": now}).fetchall()
    return [tuple(_plain(v) for v in r) for r in rows]


def run_case(case, now, conn, provider, judge, use_judges=True, run_tags=()) -> dict:
    ctx = ToolContext(conn, provider, now=now)
    inject = case.get("inject_chunks") or []
    if inject:  # a planted chunk goes through the real Prompt Shields like any retrieved text
        ctx.shield = lambda chunks, q: shields.shield([*inject, *chunks], q)
    question = case["question"]
    started = time.monotonic()
    # through the MCP server, as users get it (TOOL_TRANSPORT=direct skips the protocol);
    # the in-process server runs the tools with this case's context: its date, its shield
    tools = (
        None
        if settings.tool_transport == "direct"
        else McpTools(build_server(lambda: nullcontext(ctx)))
    )
    try:
        turn = chat(
            [*case.get("history", []), {"role": "user", "content": question}],
            replace(ctx, tools=tools),
            session_id=case["id"],
            tags=["eval", case["category"], *run_tags],
        )
    finally:
        if tools:
            tools.close()
    latency_ms = int((time.monotonic() - started) * 1000)
    t = ev.transcript(question, turn.answer, turn.messages)
    t["cited"], t["dropped"] = turn.sources, turn.dropped_markers
    rows = golden_rows(conn, case, now)
    prompt_numbers = ev.numbers(system_prompt(ctx, turn.prompt_version))
    judge_cost = 0.0
    checks: dict[str, ev.Check] = {}
    for name in case.get("checks", []):
        if name in JUDGED and not use_judges:
            checks[name] = ev.Check(None, detail="judges off")
        elif name == "tool_selection":
            checks[name] = ev.tool_selection(case, t, conn)
        elif name == "exact_answer":
            checks[name] = ev.exact_answer(case, t, rows)
        elif name == "no_ungrounded_numbers":
            checks[name] = ev.no_ungrounded_numbers(case, t, prompt_numbers)
        elif name == "citation":
            checks[name] = ev.citation(case, t)
        elif name == "retrieval":
            hits = search(conn, provider, question, k=20)
            checks[name] = ev.retrieval(case, ev.top_articles(hits))
        elif name == "groundedness":
            checks[name], cost = judges.groundedness(case, t)
            judge_cost = None if cost is None or judge_cost is None else judge_cost + cost
            checks["citation_support"] = judges.citation_support(judge, case, t)
        elif name == "guardrail":
            checks[name] = judges.guardrail(judge, case, t)
    applicable = [c.passed for c in checks.values() if c.passed is not None]
    for name, check in checks.items():  # each check as a score on the case's trace
        if check.passed is not None:
            tracing.score(turn.trace_id, f"eval:{name}", float(check.passed))
    u, j = provider.usage, judge.usage
    if judge_cost is not None:
        judge_cost = None if j["cost_usd"] is None else judge_cost + j["cost_usd"]
    return {
        "id": case["id"],
        "category": case["category"],
        "question": question,
        "answer": turn.answer,
        "sources": turn.sources,
        "dropped_markers": turn.dropped_markers,
        "tool_calls": [{"name": c["name"], "arguments": c["arguments"]} for c in t["calls"]],
        "checks": {k: v.as_dict() for k, v in checks.items()},
        "passed": bool(applicable) and all(applicable),
        "latency_ms": latency_ms,
        "tokens": {"prompt": u["prompt_tokens"], "completion": u["completion_tokens"]},
        "cost_usd": u["cost_usd"],
        "judge_cost_usd": judge_cost,
    }


def _error_result(case: dict, e: Exception) -> dict:
    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "answer": "",
        "tool_calls": [],
        "checks": {},
        "passed": False,
        "latency_ms": None,
        "tokens": {"prompt": 0, "completion": 0},
        "cost_usd": 0.0,
        "judge_cost_usd": 0.0,
        "error": f"{type(e).__name__}: {e}",
    }


def run(
    cases,
    now,
    max_cost=3.0,
    concurrency=2,
    use_judges=True,
    make_conn=get_connection,
    make_provider=None,
    make_judge=None,
    run_tags=(),
) -> tuple[list[dict], bool]:
    """Returns (results, stopped_by_cost_cap). Cases start only while spend is under max_cost."""
    make_provider = make_provider or (
        lambda conn: AzureOpenAIProvider(conn, purpose_prefix="eval:")
    )
    make_judge = make_judge or (
        lambda conn: AzureOpenAIProvider(
            conn,
            chat_deployment=settings.eval_judge_deployment or None,
            purpose_prefix="eval:",
            max_completion_tokens=2000,
        )
    )
    lock = threading.Lock()
    spent = {"usd": 0.0, "capped": False}

    def job(case):
        with lock:
            if spent["usd"] >= max_cost:
                spent["capped"] = True
                return None
        conn = make_conn()
        try:
            result = run_case(
                case, now, conn, make_provider(conn), make_judge(conn), use_judges, run_tags
            )
        except Exception as e:  # one broken case must not stop the run
            result = _error_result(case, e)
        finally:
            conn.close()
        with lock:
            spent["usd"] += (result["cost_usd"] or 0) + (result["judge_cost_usd"] or 0)
        status = "PASS" if result["passed"] else "FAIL"
        line = f"{status}  {case['id']:<22} {case['question'][:60]}"
        print("\n".join([line, *why_failed(result)]), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = [r for r in pool.map(job, cases) if r is not None]
    return results, spent["capped"]


def why_failed(result: dict) -> list[str]:
    """Indented lines under a FAIL: each failing check and the start of the answer, so a CI
    log shows why without downloading the results file."""
    if result["passed"]:
        return []
    out = [
        f"      {k}: {(c.get('detail') or '')[:200]}"
        for k, c in result.get("checks", {}).items()
        if c.get("passed") is False
    ]
    if result.get("error"):
        out.append(f"      error: {str(result['error'])[:200]}")
    calls = ", ".join(c["name"] for c in result.get("tool_calls", [])) or "none"
    answer = (result.get("answer") or "")[:200].replace("\n", " ")
    return [*out, f"      tools: {calls}", f"      answer: {answer}"]


def _pct(values, q):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def summarize(results: list[dict]) -> dict:
    by_cat: dict[str, list[bool]] = {}
    by_eval: dict[str, list[dict]] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r["passed"])
        for name, c in r["checks"].items():
            if c["passed"] is not None:
                by_eval.setdefault(name, []).append(c)
    costs = [r["cost_usd"] for r in results]
    judge_costs = [r["judge_cost_usd"] for r in results]
    retrieval = by_eval.get("retrieval", [])
    return {
        "cases": len(results),
        "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3) if results else 0,
        "categories": {
            k: {"n": len(v), "pass_rate": round(sum(v) / len(v), 3)}
            for k, v in sorted(by_cat.items())
        },
        "evaluators": {
            k: {
                "n": len(v),
                "pass_rate": round(sum(c["passed"] for c in v) / len(v), 3),
                "mean_score": round(statistics.mean(c["score"] or 0 for c in v), 3),
            }
            for k, v in sorted(by_eval.items())
        },
        "retrieval": {
            "hit_at_5": round(sum(c["passed"] for c in retrieval) / len(retrieval), 3),
            "mrr": round(statistics.mean(c["score"] for c in retrieval), 3),
        }
        if retrieval
        else None,
        "cost_usd": None if None in costs else round(sum(costs), 4),
        "judge_cost_usd": None if None in judge_costs else round(sum(judge_costs), 4),
        "latency_ms": {
            "p50": _pct([r["latency_ms"] for r in results], 0.5),
            "p95": _pct([r["latency_ms"] for r in results], 0.95),
        },
        "errors": sum("error" in r for r in results),
    }


def below_thresholds(summary: dict, thresholds: dict) -> list[str]:
    """Checks the global minimums, every evaluator, and the categories present in this run."""
    fails = []
    if summary["pass_rate"] < thresholds.get("overall_pass_rate", 0):
        fails.append(f"overall {summary['pass_rate']} < {thresholds['overall_pass_rate']}")
    for name, minimum in (thresholds.get("evaluators") or {}).items():
        got = summary["evaluators"].get(name)
        if got and got["pass_rate"] < minimum:
            fails.append(f"evaluator {name} {got['pass_rate']} < {minimum}")
    for name, minimum in (thresholds.get("retrieval") or {}).items():
        got = (summary.get("retrieval") or {}).get(name)
        if got is not None and got < minimum:
            fails.append(f"retrieval {name} {got} < {minimum}")
    for cat, minimum in (thresholds.get("categories") or {}).items():
        got = summary["categories"].get(cat)
        if got and got["pass_rate"] < minimum:
            fails.append(f"category {cat} {got['pass_rate']} < {minimum}")
    return fails


def record_run(meta: dict, summary: dict, passed: bool, make_conn=get_connection) -> bool:
    """Keep the run's totals in eval_runs for the AI Ops dashboard. False if not stored."""
    try:
        with make_conn() as conn:
            conn.execute(
                "INSERT INTO public.eval_runs (run_at, dataset, subset, prompt_version, "
                "chat_deployment, cases, pass_rate, cost_usd, judge_cost_usd, latency_p50_ms, "
                "latency_p95_ms, passed_thresholds, summary) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    datetime.strptime(meta["run_at"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC),
                    meta["dataset"],
                    meta["subset"],
                    meta["prompt_version"],
                    meta["chat_deployment"],
                    summary["cases"],
                    summary["pass_rate"],
                    summary["cost_usd"],
                    summary["judge_cost_usd"],
                    summary["latency_ms"]["p50"],
                    summary["latency_ms"]["p95"],
                    passed,
                    Jsonb(summary),
                ),
            )
        return True
    except psycopg.Error as e:  # the result file and report are still written
        print(f"eval run not stored for the dashboard: {type(e).__name__}")
        return False


def _fmt(x):
    return "" if x is None else f"{x:.0%}"


def compare(a: dict, b: dict) -> str:
    """Markdown diff of two result files: b relative to a."""
    sa, sb = a["summary"], b["summary"]
    lines = [
        f"Comparing `{b['meta']['file']}` against `{a['meta']['file']}`.",
        "",
        f"Overall pass rate: {sa['pass_rate']:.0%} -> {sb['pass_rate']:.0%}",
        "",
        "| Category | Before | After | Change |",
        "|---|---|---|---|",
    ]
    for cat in sorted(set(sa["categories"]) | set(sb["categories"])):
        x = sa["categories"].get(cat, {}).get("pass_rate")
        y = sb["categories"].get(cat, {}).get("pass_rate")
        delta = f"{(y - x) * 100:+.0f} pts" if x is not None and y is not None else ""
        lines.append(f"| {cat} | {_fmt(x)} | {_fmt(y)} | {delta} |")
    lines += ["", "| Evaluator | Before | After |", "|---|---|---|"]
    for name in sorted(set(sa["evaluators"]) | set(sb["evaluators"])):
        x = sa["evaluators"].get(name, {}).get("pass_rate")
        y = sb["evaluators"].get(name, {}).get("pass_rate")
        lines.append(f"| {name} | {_fmt(x)} | {_fmt(y)} |")
    before = {r["id"]: r["passed"] for r in a["results"]}
    after = {r["id"]: r["passed"] for r in b["results"]}
    fixed = sorted(i for i in after if after[i] and before.get(i) is False)
    broke = sorted(i for i in after if not after[i] and before.get(i) is True)
    lines += [
        "",
        f"Now passing ({len(fixed)}): {', '.join(fixed) or 'none'}",
        "",
        f"Newly failing ({len(broke)}): {', '.join(broke) or 'none'}",
    ]
    return "\n".join(lines)


def report(meta, summary, results, fails, comparison=None) -> str:
    s = summary
    subset = f" (subset `{meta['subset']}`)" if meta["subset"] else ""
    verdict = "all met." if not fails else "**below threshold:** " + "; ".join(fails)
    capped = " Stopped early by the cost cap." if meta["capped"] else ""
    out = [
        "# Eval results",
        "",
        f"Dataset `{meta['dataset']}`{subset}, prompt `{meta['prompt_version']}`, chat model "
        f"`{meta['chat_deployment']}`, judge `{meta['judge_deployment']}`. Run {meta['run_at']}, "
        f"eval date {meta['eval_date']}. Raw results: `{meta['file']}` (not committed).",
        "",
        f"**{s['cases']} cases, {s['pass_rate']:.0%} passed.** Thresholds: {verdict}",
        "",
        f"Cost: chat ${s['cost_usd']}, judges ${s['judge_cost_usd']}. Latency per case: "
        f"p50 {s['latency_ms']['p50']} ms, p95 {s['latency_ms']['p95']} ms. "
        f"Errors: {s['errors']}.{capped}",
        "",
        "## Per category",
        "",
        "| Category | Cases | Pass rate |",
        "|---|---|---|",
    ]
    out += [f"| {k} | {v['n']} | {v['pass_rate']:.0%} |" for k, v in s["categories"].items()]
    out += [
        "",
        "## Per evaluator",
        "",
        "| Evaluator | Applicable | Pass rate | Mean score |",
        "|---|---|---|---|",
    ]
    out += [
        f"| {k} | {v['n']} | {v['pass_rate']:.0%} | {v['mean_score']:.2f} |"
        for k, v in s["evaluators"].items()
    ]
    if s["retrieval"]:
        out += [
            "",
            f"Retrieval over the news cases: hit@5 {s['retrieval']['hit_at_5']:.2f}, "
            f"MRR {s['retrieval']['mrr']:.2f}.",
        ]
    failed = sorted(
        (r for r in results if not r["passed"]),
        key=lambda r: -sum(c["passed"] is False for c in r["checks"].values()),
    )
    out += [
        "",
        "## Worst cases",
        "",
        "| Case | Question | Answer (start) | Failing checks |",
        "|---|---|---|---|",
    ]
    for r in failed[:10]:
        bad = "; ".join(
            f"**{k}**: {c['detail'][:140]}" for k, c in r["checks"].items() if c["passed"] is False
        ) or r.get("error", "")
        answer = r["answer"][:160].replace("\n", " ").replace("|", "/")
        out.append(f"| {r['id']} | {r['question']} | {answer} | {bad.replace('|', '/')} |")
    if comparison:
        out += ["", "## Compared with the previous run", "", comparison]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.run")
    ap.add_argument("--dataset", default="chat_v1")
    ap.add_argument("--subset", help="only cases with this tag, e.g. smoke")
    ap.add_argument("--category")
    ap.add_argument("--max-cost-usd", type=float, default=3.0)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--eval-date", help="ISO datetime that 'last weekend' etc. resolve against")
    ap.add_argument("--no-judges", action="store_true", help="skip the LLM judges")
    ap.add_argument("--baseline", help="an earlier result file to diff against in the report")
    ap.add_argument("--report", help="Markdown output (default docs/EVAL_RESULTS.md, full runs)")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args(argv)
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.compare:
        a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args.compare)
        print(compare(a, b))
        return 0

    now = datetime.fromisoformat(args.eval_date) if args.eval_date else datetime.now(UTC)
    cases = load_cases(args.dataset, args.subset, args.category)
    settings.trace_environment = "eval"  # eval traces stay apart from real chats in Langfuse
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    tags = (f"run:{stamp}", f"dataset:{args.dataset}", f"prompt:{settings.prompt_version}")
    try:
        results, capped = run(
            cases, now, args.max_cost_usd, args.concurrency, not args.no_judges, run_tags=tags
        )
    finally:
        tracing.flush()
    summary = summarize(results)
    thresholds = yaml.safe_load(THRESHOLDS.read_text()) if THRESHOLDS.exists() else {}
    thresholds = thresholds or {}
    if args.subset or args.category:  # too few cases per category for category minimums
        thresholds = {k: v for k, v in thresholds.items() if k != "categories"}
    fails = below_thresholds(summary, thresholds)
    part = f"_{args.subset or args.category}" if args.subset or args.category else ""
    RESULTS.mkdir(exist_ok=True)
    out_file = RESULTS / f"{stamp}_{args.dataset}{part}_{settings.prompt_version}.json"
    meta = {
        "dataset": args.dataset,
        "subset": args.subset or args.category,
        "prompt_version": settings.prompt_version,
        "run_at": stamp,
        "eval_date": now.isoformat(),
        "chat_deployment": settings.azure_openai_chat_deployment,
        "judge_deployment": settings.eval_judge_deployment or settings.azure_openai_chat_deployment,
        "file": f"evals/results/{out_file.name}",
        "capped": capped,
    }
    data = {"meta": meta, "summary": summary, "results": results}
    record_run(meta, summary, passed=not fails and not capped)
    out_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    comparison = None
    if args.baseline:
        base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        comparison = compare(base, data)
    full = not (args.subset or args.category)
    md_path = (
        Path(args.report) if args.report else (REPORT if full else out_file.with_suffix(".md"))
    )
    md_path.write_text(report(meta, summary, results, fails, comparison), encoding="utf-8")
    print(
        f"\n{summary['cases']} cases, pass rate {summary['pass_rate']:.0%}, chat cost "
        f"${summary['cost_usd']}, judge cost ${summary['judge_cost_usd']}"
    )
    print(f"results: {out_file}\nreport:  {md_path}")
    for f in fails:
        print(f"BELOW THRESHOLD: {f}")
    return 1 if fails or capped else 0


if __name__ == "__main__":
    sys.exit(main())
