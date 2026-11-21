"""The feedback loop: thumbs-down answers become eval cases, so a fixed problem stays fixed.

    python -m evals.feedback review                 # unreviewed thumbs-down turns -> logs/
    python -m evals.feedback promote 12 --category standings --expected-tool get_league_table
    python -m evals.feedback dismiss 13 --reason "question was about last season"

`review` writes logs/feedback_review.md (gitignored: it holds the questions and answers) with
each turn's tools, the comment, and a link to its Langfuse trace. `promote` appends the
question to evals/datasets/feedback_v1.jsonl, which `python -m evals.run --dataset
feedback_v1` runs like any other dataset; the promoted question is committed with it, so
only promote questions that are fine to publish. Either way the feedback row is marked as
reviewed, so it does not come up again.
"""

import argparse
import json
import sys
from pathlib import Path

from psycopg.rows import dict_row

from backend.config import settings
from backend.db import get_connection, init_db

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "datasets" / "feedback_v1.jsonl"
REVIEW = ROOT.parent / "logs" / "feedback_review.md"
LANGFUSE_PROJECT = "plc-chatbot"  # LANGFUSE_INIT_PROJECT_ID in docker-compose.langfuse.yml
# what a promoted case is checked on when the reviewer names no checks
DEFAULT_CHECKS = {
    "news": ["tool_selection", "citation", "groundedness"],
    "mixed_why": ["tool_selection", "citation", "groundedness", "no_ungrounded_numbers"],
    "off_topic": ["guardrail"],
    "betting": ["guardrail"],
    "prompt_injection": ["guardrail"],
}
FALLBACK_CHECKS = ["tool_selection", "no_ungrounded_numbers", "groundedness"]


def pending(conn) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT f.id, f.created_at, f.question, f.answer, f.tools, f.comment, "
            "f.prompt_version, t.trace_id FROM feedback f LEFT JOIN chat_turns t USING (turn_id) "
            "WHERE f.rating = 'down' AND f.reviewed_at IS NULL ORDER BY f.created_at"
        ).fetchall()


def trace_url(trace_id: str | None) -> str | None:
    if not trace_id or not settings.langfuse_host:
        return None
    return f"{settings.langfuse_host.rstrip('/')}/project/{LANGFUSE_PROJECT}/traces/{trace_id}"


def review_markdown(rows: list[dict]) -> str:
    out = [f"# Thumbs-down answers to review ({len(rows)})", ""]
    if not rows:
        out.append("Nothing to review.")
    for r in rows:
        tools = ", ".join(t["name"] + (" (error)" if "error" in t else "") for t in r["tools"])
        out += [
            f"## Feedback {r['id']} · {r['created_at']:%Y-%m-%d %H:%M} UTC · "
            f"prompt {r['prompt_version']}",
            "",
            f"**Question:** {r['question']}",
            "",
            f"**Answer:** {r['answer'] or '(none)'}",
            "",
            f"**Tools:** {tools or 'none'}",
            f"**Comment:** {r['comment'] or '(none)'}",
        ]
        if url := trace_url(r["trace_id"]):
            out.append(f"**Trace:** {url}")
        out += ["", f"`python -m evals.feedback promote {r['id']} --category <category>`", ""]
    return "\n".join(out)


def next_case_id(path: Path) -> str:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return f"fb-{sum(1 for line in existing if line.strip()) + 1:03d}"


def make_case(
    row: dict,
    category: str,
    expected_tools: list[str],
    checks: list[str] | None,
    note: str | None,
    path: Path,
) -> dict:
    checks = checks or DEFAULT_CHECKS.get(category, FALLBACK_CHECKS)
    if not expected_tools:
        checks = [c for c in checks if c != "tool_selection"]
    case = {
        "id": next_case_id(path),
        "dataset": "feedback_v1",
        "category": category,
        "question": row["question"],
        "expected_tools": expected_tools,
        "golden": {},
        "checks": checks,
        "tags": ["from_feedback"],
        "source": {"feedback_id": row["id"], "prompt_version": row["prompt_version"]},
    }
    if note:
        case["rubric"] = note
    return case


def promote(
    conn,
    feedback_id: int,
    category: str,
    expected_tools: list[str],
    checks: list[str] | None = None,
    note: str | None = None,
    path: Path = DATASET,
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT id, question, prompt_version, reviewed_at FROM feedback WHERE id = %s",
            (feedback_id,),
        ).fetchone()
    if row is None:
        return {"error": f"no feedback {feedback_id}"}
    if row["reviewed_at"] is not None:
        return {"error": f"feedback {feedback_id} was already reviewed"}
    case = make_case(row, category, expected_tools, checks, note, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")
    conn.execute(
        "UPDATE feedback SET reviewed_at = now(), review_outcome = 'promoted', "
        "eval_case_id = %s WHERE id = %s",
        (case["id"], feedback_id),
    )
    return {"promoted": case["id"], "to": str(path)}


def dismiss(conn, feedback_id: int, reason: str) -> dict:
    n = conn.execute(
        "UPDATE feedback SET reviewed_at = now(), review_outcome = 'dismissed', "
        "review_note = %s WHERE id = %s AND reviewed_at IS NULL",
        (reason, feedback_id),
    ).rowcount
    return {"dismissed": feedback_id} if n else {"error": f"no unreviewed feedback {feedback_id}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.feedback")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("review")
    p = sub.add_parser("promote")
    p.add_argument("feedback_id", type=int)
    p.add_argument("--category", required=True, help="a chat_v1 category, e.g. standings")
    p.add_argument("--expected-tool", action="append", default=[], dest="tools")
    p.add_argument("--check", action="append", dest="checks", help="default: by category")
    p.add_argument("--note", help="what a good answer does (used by the guardrail judge)")
    d = sub.add_parser("dismiss")
    d.add_argument("feedback_id", type=int)
    d.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    conn = get_connection()
    init_db(conn)
    if args.cmd == "review":
        rows = pending(conn)
        REVIEW.parent.mkdir(exist_ok=True)
        REVIEW.write_text(review_markdown(rows), encoding="utf-8")
        out = {"to_review": len(rows), "written": str(REVIEW)}
    elif args.cmd == "promote":
        out = promote(conn, args.feedback_id, args.category, args.tools, args.checks, args.note)
    else:
        out = dismiss(conn, args.feedback_id, args.reason)
    print(json.dumps(out, indent=1))
    return 1 if "error" in out else 0


if __name__ == "__main__":
    sys.exit(main())
