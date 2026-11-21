"""Marker validation and source resolution against the db test database. Marked db."""

import json

import pytest

from backend.llm.citations import apply, slug
from ingestion.silver import load_from_bronze
from ingestion.test_ingestion_db import fill_bronze

pytestmark = pytest.mark.db


def tool(content: dict) -> dict:
    return {"role": "tool", "tool_call_id": "x", "content": json.dumps(content)}


def test_markers_are_validated_renumbered_and_resolved(db):
    fill_bronze(db)
    load_from_bronze(db)
    messages = [tool({"results": [{"source_id": "a4764661", "title": "Arsenal 3-0 Coventry"}]}),
                tool({"match": {"match_id": 2645195, "source_id": "m2645195"}}),
                tool({"after_matchweek": 1, "source_id": "t1"})]  # fmt: skip
    answer = (
        "Arsenal won 3-0 [m2645195] and are top [t1]. Havertz starred [a4764661][m2645195]. "
        "A made-up claim [a999] and a fake match [m1]. See [the report]"
        "(https://example.com/x) or https://evil.example.com.\n\n**Sources**\n- junk"
    )
    text, sources, dropped = apply(answer, messages, db)
    assert text == ("Arsenal won 3-0 [1] and are top [2]. Havertz starred [3][1]. "
                    "A made-up claim and a fake match. See the report or.")  # fmt: skip
    assert dropped == ["a999", "m1"]
    assert [(s["n"], s["id"], s["kind"]) for s in sources] == [
        (1, "m2645195", "match"), (2, "t1", "table"), (3, "a4764661", "article"),
    ]  # fmt: skip
    assert sources[0]["url"] == "https://www.premierleague.com/en/match/2645195"
    assert sources[0]["title"] == "Arsenal 3-0 Coventry City"
    assert sources[2]["url"].endswith("/en/news/4764661/arsenal-3-0-coventry")


def test_an_id_that_no_tool_returned_is_dropped_even_if_it_exists(db):
    fill_bronze(db)
    load_from_bronze(db)
    text, sources, dropped = apply("Arsenal won [m2645195]", [], db)
    assert (text, sources, dropped) == ("Arsenal won", [], ["m2645195"])


def test_club_slug():
    assert slug("Brighton & Hove Albion") == "brighton-and-hove-albion"
    assert slug("Manchester United") == "manchester-united"
