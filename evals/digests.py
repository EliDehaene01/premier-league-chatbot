"""python -m evals.digests: evaluate the weekly digests on past weeks (digests_v1).

Each case writes a digest with the real pipeline (real data, real Prompt Shields, the Azure
deployment) without storing it, then checks it:

  code   citations, scores_match, coverage, must_mention, format, kept_rate
  judge  faithfulness: each model-written line against what its sources say

Cost: a recap is one or two calls, a news digest about ten, plus one judge call per digest.
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime, time
from pathlib import Path

import yaml

from backend.db import get_connection, init_db
from backend.llm.providers import AzureOpenAIProvider
from digests import recap as recap_facts
from digests.config import load_weights
from digests.writer import SCORE, DigestError, recap_index, write_news, write_recap
from evals.evaluators import Check

DATASET = Path(__file__).parent / "datasets" / "digests_v1.jsonl"
THRESHOLDS = Path(__file__).parent / "digest_thresholds.yaml"
RESULTS = Path(__file__).parent / "results"
JUDGE_PROMPT = """You check a weekly Premier League digest line by line. Each line lists the
source records it cites (match data, the league table, or article text). A line is supported
only if every fact in it is in its cited sources. Wording and emphasis may differ.

Lines and their sources:
{lines}

Reply with JSON only: {{"unsupported": [<line numbers>], "reason": "<one sentence>"}}"""


def model_lines(d: dict) -> list[dict]:
    lines = [d["intro"]] if d.get("intro") else []
    return lines + [
        b for s in d["sections"] if s.get("generated_by") != "code" for b in s["bullets"]
    ]


def check_citations(d: dict) -> Check:
    lines = model_lines(d)
    bad = [x["text"][:60] for x in lines if not x.get("cites")]
    return Check(not bad, 1 - len(bad) / max(len(lines), 1), f"uncited: {bad}" if bad else "")


def check_scores(d: dict, index: dict) -> Check:
    wrong = []
    for x in model_lines(d):
        known = {str(index[s].get("score")) for s in x["sources"] if isinstance(index.get(s), dict)}
        known |= {"-".join(reversed(k.split("-"))) for k in known if "-" in k}
        wrong += [
            m.group(0)
            for m in SCORE.finditer(x["text"])
            if known - {"None"} and m.group(0) not in known
        ]
    return Check(not wrong, None, f"scores not in their match: {wrong}" if wrong else "")


def check_coverage(d: dict, facts: dict | None) -> Check:
    if d["kind"] != "matchweek_recap":
        return Check(None, detail="recap only")
    cited = {s for sec in d["sections"] for b in sec["bullets"] for s in b["sources"]}
    missing = [f["source_id"] for f in facts["results"] if f["source_id"] not in cited]
    return Check(
        not missing,
        1 - len(missing) / len(facts["results"]),
        f"fixtures missing: {missing}" if missing else "",
    )


def check_mentions(d: dict, case: dict) -> Check:
    wanted = case.get("must_mention") or []
    if not wanted:
        return Check(None, detail="nothing labelled")
    text = " ".join([d["headline"], *(x["text"] for x in model_lines(d))]).lower()
    missing = [w for w in wanted if w.lower() not in text]
    return Check(
        not missing, 1 - len(missing) / len(wanted), f"missing: {missing}" if missing else ""
    )


def check_format(d: dict) -> Check:
    problems = []
    if len(d["headline"]) > 90:
        problems.append(f"headline {len(d['headline'])} chars")
    written = [s for s in d["sections"] if s.get("generated_by") != "code"]
    lo, hi = (3, 4) if d["kind"] == "matchweek_recap" else (5, 8)
    if not lo <= len(written) <= hi:
        problems.append(f"{len(written)} sections, expected {lo}-{hi}")
    if any(len(s["bullets"]) > 5 for s in written):
        problems.append("a section has more than 5 bullets")
    return Check(not problems, None, "; ".join(problems))


def check_kept(d: dict) -> Check:
    kept, dropped = len(model_lines(d)), len(d["checks"]["dropped"])
    rate = kept / max(kept + dropped, 1)
    return Check(rate >= 0.9, rate, f"{dropped} dropped" if dropped else "")


def judge_faithfulness(judge, d: dict, index: dict) -> tuple[Check, float | None]:
    lines = model_lines(d)
    if not lines:
        return Check(False, 0.0, "no model-written lines"), 0.0
    blocks = []
    for i, x in enumerate(lines, 1):
        srcs = json.dumps({s: index.get(s) for s in x["sources"]}, default=str)[:4000]
        blocks.append(f"[{i}] {x['text']}\n    sources: {srcs}")
    r = judge.chat(
        [{"role": "user", "content": JUDGE_PROMPT.format(lines="\n".join(blocks))}],
        purpose="eval:digest_judge",
    )
    try:
        verdict = json.loads(re.search(r"\{.*\}", r.content or "", re.S).group(0))
        bad = [int(n) for n in verdict.get("unsupported", [])]
    except (AttributeError, ValueError, TypeError):
        return Check(False, 0.0, "judge gave no verdict"), r.cost_usd
    score = 1 - len(set(bad)) / len(lines)
    return Check(
        not bad, score, f"unsupported lines {bad}: {verdict.get('reason', '')}"[:200]
    ), r.cost_usd


def run_case(case: dict, conn, weights: dict, use_judges: bool) -> dict:
    provider = AzureOpenAIProvider(conn, purpose_prefix="eval:")
    facts = index = None
    if case["kind"] == "matchweek_recap":
        d = write_recap(conn, provider, case["matchweek"], cfg=weights["recap"], store=False)
        facts = recap_facts.gather(conn, case["matchweek"], cfg=weights["recap"])
        index = recap_index(facts)
    else:
        end = datetime.combine(datetime.fromisoformat(case["week_ending"]).date(), time(5), UTC)
        d = write_news(conn, provider, end, cfg=weights["news"], store=False)
        index = {s["id"]: {"title": s["title"]} for s in d["sources"]}
        index |= {k: v for k, v in _article_texts(conn, d).items()}
    checks = {
        "citations": check_citations(d),
        "scores_match": check_scores(d, index),
        "coverage": check_coverage(d, facts),
        "must_mention": check_mentions(d, case),
        "format": check_format(d),
        "kept_rate": check_kept(d),
    }
    cost = d["cost_usd"]
    if use_judges:
        checks["faithfulness"], judge_cost = judge_faithfulness(provider, d, index)
        cost = None if cost is None or judge_cost is None else cost + judge_cost
    return {
        "id": case["id"],
        "headline": d["headline"],
        "cost_usd": cost,
        "dropped": d["checks"]["dropped"],
        "checks": {k: v.as_dict() for k, v in checks.items()},
    }


def _article_texts(conn, d: dict) -> dict:
    ids = [int(s["id"][1:]) for s in d["sources"] if s["id"].startswith("a")]
    rows = conn.execute(
        "SELECT content_id, title, coalesce(body_text, description) FROM silver.articles "
        "WHERE content_id = ANY(%s)",
        (ids,),
    ).fetchall()
    return {f"a{cid}": {"title": t, "text": (body or "")[:3000]} for cid, t, body in rows}


def summarize(results: list[dict]) -> dict:
    out = {}
    for r in results:
        for name, c in r.get("checks", {}).items():
            if c["passed"] is not None:
                out.setdefault(name, []).append(c["passed"])
    return {k: round(sum(v) / len(v), 3) for k, v in out.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.digests")
    ap.add_argument("--case", help="run one case by id")
    ap.add_argument("--no-judges", action="store_true")
    args = ap.parse_args(argv)
    cases = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
    conn = get_connection()
    init_db(conn)
    weights = load_weights()
    results = []
    for case in cases:
        try:
            results.append(run_case(case, conn, weights, not args.no_judges))
        except DigestError as e:
            results.append({"id": case["id"], "error": str(e), "checks": {}})
        print(json.dumps({k: results[-1].get(k) for k in ("id", "headline", "error", "cost_usd")}))
    summary = summarize(results)
    limits = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))["checks"]
    fails = [
        f"{k} {v:.2f} < {limits[k]}"
        for k, v in summary.items()
        if limits.get(k) is not None and v < limits[k]
    ]
    fails += [f"{r['id']}: {r['error']}" for r in results if r.get("error")]
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (RESULTS / f"digests-{stamp}.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, default=str)
    )
    print(json.dumps({"summary": summary, "below_threshold": fails}, indent=2))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
