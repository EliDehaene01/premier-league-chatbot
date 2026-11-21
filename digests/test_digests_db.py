"""Digests end to end on the db test database, with a scripted model. Marked db."""

import json
from datetime import UTC, datetime

import pytest

from backend.llm.fake_provider import FakeProvider
from backend.llm.providers import ChatResult
from backend.rag.build_index import build_index
from backend.rag.shields import ShieldResult
from digests import recap, site
from digests.writer import DigestError, write_news, write_recap
from ingestion.silver import load_from_bronze
from ingestion.test_ingestion_db import fill_bronze

pytestmark = pytest.mark.db
NOW = datetime(2026, 8, 26, 5, tzinfo=UTC)


@pytest.fixture
def seeded(db):
    fill_bronze(db)
    load_from_bronze(db)
    return db


def reply(obj) -> ChatResult:
    return ChatResult(json.dumps(obj), cost_usd=0.001)


def cited(text, *sources):
    return {"text": text, "sources": list(sources)}


def test_recap_facts(seeded):
    f = recap.gather(seeded, now=NOW)
    assert f["matchweek"] == 1 and [r["score"] for r in f["results"]] == ["3-0"]
    assert f["table"]["rows"][0]["club"] == "Arsenal" and f["table"]["rows"][0]["points"] == 3
    assert f["highlights"]["clean_sheets"] == [{"source_id": "m2645195", "club": "Arsenal"}]
    assert recap.gather(seeded, matchweek=2, now=NOW)["error"]


def test_write_recap_validates_retries_and_stores(seeded):
    bad = {
        "headline": "Arsenal hit 5",
        "intro": cited("Arsenal won 3-0.", "m2645195"),
        "sections": [
            {
                "title": "Top",
                "bullets": [cited("Arsenal lead on 9 points.", "t1"), cited("Invented.", "m1")],
            }
        ],
    }
    good = {
        "headline": "Arsenal start with a 3-0 win",
        "intro": cited("Arsenal beat Coventry City 3-0.", "m2645195"),
        "sections": [
            {
                "title": "Top",
                "bullets": [cited("Arsenal top the table on 3 points.", "t1", "m2645195")],
            }
        ],
    }
    provider = FakeProvider([reply(bad), reply(good)])
    d = write_recap(seeded, provider, now=NOW)
    assert len(provider.chat_calls) == 2  # the first draft lost bullets, so it retried
    assert provider.chat_calls[0]["response_format"]["json_schema"]["strict"] is True
    assert d["headline"] == "Arsenal start with a 3-0 win" and d["checks"]["dropped"] == []
    assert d["sections"][-1]["title"] == "All results"
    assert [s["id"] for s in d["sources"]] == ["m2645195", "t1"]
    assert d["sections"][0]["bullets"][0]["cites"] == [2, 1]
    row = seeded.execute("SELECT kind, period_key, headline, cost_usd FROM digests").fetchone()
    assert row[:3] == ("matchweek_recap", "mw1", d["headline"]) and float(row[3]) == 0.002


def test_write_recap_keeps_the_better_draft_when_both_fail(seeded):
    bad = {
        "headline": "Arsenal hit 5",
        "intro": cited("Arsenal won 3-0.", "m2645195"),
        "sections": [{"title": "Top", "bullets": [cited("Invented.", "m1")]}],
    }
    d = write_recap(seeded, FakeProvider([reply(bad), reply(bad)]), now=NOW, store=False)
    assert d["headline"] == "Matchweek 1 recap"  # "5" was in no fact
    assert [x["where"] for x in d["checks"]["dropped"]] == ["Top[0]", "headline"]
    assert [s["title"] for s in d["sections"]] == ["All results"]


def test_write_news(seeded):
    build_index(seeded, FakeProvider())
    script = [
        reply({"labels": [{"story": 0, "type": "match_reaction"}]}),
        reply(
            {
                "title": "Arsenal open with a win",
                "summary": cited("Arsenal won 3-0.", "a4764661"),
                "bullets": [cited("A made-up 7-goal claim.", "a4764661")],
            }
        ),
        reply(
            {"headline": "Arsenal's opening win", "intro": cited("Arsenal began well.", "a4764661")}
        ),
    ]
    seen = []

    def shields(docs, q):
        seen.extend(d["content_id"] for d in docs)
        return ShieldResult(safe=list(docs))

    d = write_news(
        seeded,
        FakeProvider(script),
        NOW,
        {"window_days": 7, "stories": 7, "score": {"coverage": 1, "recency": 1, "type": {}}},
        shield_fn=shields,
    )
    assert seen == [4764661]  # fantasy left out, and every article checked before the model
    assert d["headline"] == "Arsenal's opening win" and len(d["sections"]) == 1
    assert d["checks"]["dropped"][0]["reason"].startswith("numbers not in its sources")
    assert d["sources"][0]["url"].startswith("https://www.premierleague.com")


def test_news_fails_closed_when_shields_are_down(seeded):
    with pytest.raises(DigestError, match="Prompt Shields"):
        write_news(
            seeded,
            FakeProvider(),
            NOW,
            {"window_days": 7},
            shield_fn=lambda d, q: ShieldResult(error="timeout"),
        )


def test_site_renders_stored_digests(seeded, tmp_path):
    good = {
        "headline": "Arsenal start with a 3-0 win",
        "intro": cited("Arsenal beat Coventry City 3-0.", "m2645195"),
        "sections": [],
    }
    write_recap(seeded, FakeProvider([reply(good)]), now=NOW)
    files = site.render(seeded, showcase_dir=tmp_path)
    assert "digests/matchweek-recap-mw1.html" in files
    assert b"Arsenal start with a 3-0 win" in files["index.html"]
    assert b"premierleague.com/en/match/2645195" in files["digests/matchweek-recap-mw1.html"]
