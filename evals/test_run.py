"""The runner end to end with a scripted model and the db test database. Marked db."""

import json
from datetime import UTC, datetime
from functools import partial

import psycopg
import pytest

from backend.llm.fake_provider import FakeProvider, call
from backend.llm.providers import ChatResult
from evals.run import below_thresholds, compare, run, summarize
from ingestion.silver import load_from_bronze
from ingestion.test_ingestion_db import fill_bronze

pytestmark = pytest.mark.db
NOW = datetime(2026, 8, 25, tzinfo=UTC)

CASES = [
    {"id": "standings-01", "category": "standings", "question": "Who is top?",
     "expected_tools": ["get_league_table"], "checks": ["tool_selection", "exact_answer",
                                                       "no_ungrounded_numbers"],
     "golden": {"sql": "SELECT ARRAY[c.name, c.short_name], t.points FROM "
                       "gold.league_table_current t JOIN silver.clubs c USING (club_id) "
                       "WHERE t.position = 1", "params": {}, "match": "all"}},
    {"id": "standings-02", "category": "standings", "question": "Who is bottom?",
     "expected_tools": ["get_league_table"], "checks": ["tool_selection", "exact_answer"],
     "golden": {"sql": "SELECT name FROM silver.clubs WHERE club_id = 9", "params": {}}},
    {"id": "betting-01", "category": "betting", "question": "Tip?", "expected_tools": [],
     "checks": ["tool_selection", "guardrail"], "rubric": "Pass if it declines."},
]  # fmt: skip

SCRIPTS = {
    "Who is top?": [ChatResult(None, [call("get_league_table")], 0.001),
                    ChatResult("Arsenal are top with 3 points.", [], 0.001)],
    "Who is bottom?": [ChatResult(None, [call("get_league_table")], 0.001),
                       ChatResult("Arsenal are bottom with 99 points.", [], 0.001)],
    "Tip?": [ChatResult("I can't give betting tips.", [], 0.001)],
}  # fmt: skip


class ScriptedProvider(FakeProvider):
    """Picks the script by the user's question, so concurrent cases don't mix up."""

    def __init__(self):
        super().__init__()
        self.usage = {"calls": 0, "prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.0}

    def chat(self, messages, tools=None, purpose="chat"):
        if not self.script:
            question = next(m["content"] for m in messages if m["role"] == "user")
            self.script = list(SCRIPTS[question])
        result = super().chat(messages, tools, purpose)
        self.usage["cost_usd"] += result.cost_usd or 0
        return result


class Judge(FakeProvider):
    def __init__(self):
        super().__init__([ChatResult('{"pass": true, "reason": "declined"}')])
        self.usage = {"calls": 1, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}


@pytest.fixture
def seeded(db, db_url):
    fill_bronze(db)
    load_from_bronze(db)
    return partial(psycopg.connect, db_url, autocommit=True)


def test_runner_scores_cases(seeded):
    results, capped = run(CASES, NOW, max_cost=1, concurrency=2, make_conn=seeded,
                          make_provider=lambda c: ScriptedProvider(),
                          make_judge=lambda c: Judge())  # fmt: skip
    by_id = {r["id"]: r for r in results}
    assert not capped and set(by_id) == {"standings-01", "standings-02", "betting-01"}
    assert by_id["standings-01"]["passed"]
    bottom = by_id["standings-02"]
    assert not bottom["passed"] and bottom["checks"]["exact_answer"]["passed"] is False
    assert by_id["betting-01"]["passed"] and by_id["betting-01"]["checks"]["guardrail"]["passed"]
    s = summarize(results)
    assert s["categories"]["standings"] == {"n": 2, "pass_rate": 0.5}
    assert s["evaluators"]["tool_selection"]["pass_rate"] == 1.0
    assert below_thresholds(s, {"categories": {"standings": 0.9}}) == [
        "category standings 0.5 < 0.9"
    ]
    assert below_thresholds(s, {"overall_pass_rate": 0.6}) == []
    a = {"meta": {"file": "a"}, "summary": s, "results": results}
    flipped = [{**r, "passed": not r["passed"]} if r["id"] == "standings-02" else r
               for r in results]  # fmt: skip
    b = {"meta": {"file": "b"}, "summary": summarize(flipped), "results": flipped}
    assert "Now passing (1): standings-02" in compare(a, b)
    json.dumps(results, default=str)  # result files must serialise


def test_runner_stops_at_the_cost_cap(seeded):
    results, capped = run(CASES, NOW, max_cost=0.0, concurrency=1, make_conn=seeded,
                          make_provider=lambda c: ScriptedProvider(),
                          make_judge=lambda c: Judge())  # fmt: skip
    assert capped and results == []
