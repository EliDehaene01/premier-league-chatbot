"""The AI Ops page from a few rows. Marked db."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.observability import dashboard

pytestmark = pytest.mark.db
NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


def test_totals_only_and_nothing_private(db):
    for purpose, cost in (("chat", 0.01), ("eval:chat", 0.02), ("digest:recap", 0.005)):
        db.execute(
            "INSERT INTO llm_calls (called_at, kind, model, prompt_tokens, completion_tokens, "
            "cost_usd, purpose) VALUES (%s, 'chat', 'm', 100, 10, %s, %s)",
            (NOW - timedelta(days=1), cost, purpose),
        )
    db.execute(
        "INSERT INTO chat_turns (turn_id, conversation_id, created_at, question, answer, "
        "latency_ms, cost_usd) VALUES (gen_random_uuid(), 'c', %s, 'my secret question', "
        "'secret answer', 4000, 0.01)",
        (NOW - timedelta(days=1),),
    )
    data = dashboard.gather(db, NOW)
    assert round(data["total_cost"], 3) == 0.035 and len(data["daily_cost"]) == 28
    assert {a["area"] for a in data["by_area"]} == {"Chat", "Evals", "Weekly digests"}
    assert data["turns"]["turns"] == 1
    page = dashboard.render_body(data)
    assert "$0.035" in page and "Daily spend" in page
    assert "secret" not in page


def test_empty_database_still_renders(db):
    page = dashboard.render_body(dashboard.gather(db, NOW))
    assert "No eval runs recorded yet." in page and "–" in page
