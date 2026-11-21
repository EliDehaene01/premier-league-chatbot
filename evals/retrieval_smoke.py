"""python -m evals.retrieval_smoke: hit rate at 5 and MRR on hand-labelled queries.

A sanity check of hybrid retrieval on the real index, not the Phase 3 eval suite.
"""

import json
import sys
from pathlib import Path

from backend.db import get_connection
from backend.llm.providers import AzureOpenAIProvider
from backend.rag.retrieval import search

CASES = Path(__file__).with_name("retrieval_smoke.jsonl")


def top_articles(hits: list[dict], n: int = 5) -> list[int]:
    seen: list[int] = []
    for h in hits:
        if h["article_id"] not in seen:
            seen.append(h["article_id"])
    return seen[:n]


def main() -> int:
    conn = get_connection()
    provider = AzureOpenAIProvider(conn)
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]
    hits = rr = 0.0
    for case in cases:
        ranked = top_articles(search(conn, provider, case["query"], k=20))
        rank = next((i for i, a in enumerate(ranked, 1) if a in case["expected"]), None)
        hits += rank is not None
        rr += 1 / rank if rank else 0
        print(f"{'rank ' + str(rank) if rank else 'MISS  '}  {case['query']}")
    print(f"\nhit@5 {hits / len(cases):.2f}   MRR {rr / len(cases):.2f}   ({len(cases)} queries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
