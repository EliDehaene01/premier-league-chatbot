"""Thumbs-down review and promotion into feedback_v1. Marked db."""

import json

import pytest

from evals import feedback

pytestmark = pytest.mark.db


@pytest.fixture
def down(db):
    db.execute(
        "INSERT INTO chat_turns (turn_id, conversation_id, question, answer, tools, trace_id) "
        "VALUES ('00000000-0000-0000-0000-000000000001', 'c', 'Who is top?', 'Spurs.', "
        "'[{\"name\": \"get_league_table\"}]', 'abc')"
    )
    return db.execute(
        "INSERT INTO feedback (turn_id, conversation_id, rating, comment, question, answer, "
        "tools, prompt_version) SELECT turn_id, conversation_id, 'down', 'wrong club', "
        "question, answer, tools, 'v2' FROM chat_turns RETURNING id"
    ).fetchone()[0]


def test_review_lists_thumbs_down_with_trace(db, down, monkeypatch):
    monkeypatch.setattr(feedback.settings, "langfuse_host", "http://localhost:3000")
    rows = feedback.pending(db)
    assert [r["id"] for r in rows] == [down]
    md = feedback.review_markdown(rows)
    assert "Who is top?" in md and "wrong club" in md and "get_league_table" in md
    assert "/project/plc-chatbot/traces/abc" in md


def test_promote_appends_a_case_once(db, down, tmp_path):
    path = tmp_path / "feedback_v1.jsonl"
    out = feedback.promote(db, down, "standings", ["get_league_table"], path=path)
    assert out["promoted"] == "fb-001"
    (case,) = [json.loads(line) for line in path.read_text().splitlines()]
    assert case["question"] == "Who is top?" and case["expected_tools"] == ["get_league_table"]
    assert case["checks"] == feedback.FALLBACK_CHECKS and case["source"]["feedback_id"] == down
    assert feedback.pending(db) == []
    assert "already reviewed" in feedback.promote(db, down, "standings", [], path=path)["error"]


def test_dismiss(db, down):
    assert feedback.dismiss(db, down, "not a bug") == {"dismissed": down}
    assert feedback.pending(db) == [] and "error" in feedback.dismiss(db, down, "again")
