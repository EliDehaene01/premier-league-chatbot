"""Each tool against the db test database, seeded from ingestion/sample_payloads. Marked db."""

from datetime import UTC, datetime

import pytest

from backend.llm.fake_provider import FakeProvider
from backend.rag.build_index import build_index
from backend.rag.shields import ShieldResult
from backend.tools import TOOL_SPECS, TOOLS, ToolContext, run_tool
from ingestion.silver import load_from_bronze
from ingestion.test_ingestion_db import fill_bronze

pytestmark = pytest.mark.db


@pytest.fixture
def ctx(db):
    fill_bronze(db)
    load_from_bronze(db)
    provider = FakeProvider()
    build_index(db, provider)
    return ToolContext(db, provider, now=datetime(2026, 8, 25, tzinfo=UTC),
                       shield=lambda chunks, q: ShieldResult(safe=list(chunks)))  # fmt: skip


def test_every_tool_has_a_schema():
    assert {s["function"]["name"] for s in TOOL_SPECS} == set(TOOLS)


def test_league_table(ctx):
    out = run_tool(ctx, "get_league_table", {})
    assert out["after_matchweek"] == 1
    assert [(r["position"], r["club"], r["points"]) for r in out["table"]] == [
        (1, "Arsenal", 3), (2, "Coventry City", 0),
    ]  # fmt: skip
    assert run_tool(ctx, "get_league_table", {"as_of_matchweek": 7})["available_matchweeks"] == [1]


def test_fixtures_and_results(ctx):
    (fixture,) = run_tool(ctx, "get_fixtures", {"club": "Gunners"})["fixtures"]
    assert (fixture["home_club"], fixture["away_club"]) == ("Coventry City", "Arsenal")
    (result,) = run_tool(ctx, "get_results", {"club": "COV"})["results"]
    assert (result["home_score"], result["away_score"]) == (3, 0)
    assert run_tool(ctx, "get_results", {"matchweek": 2})["results"] == []
    assert "error" in run_tool(ctx, "get_results", {"club": "Wolves"})


def test_match_details_by_clubs(ctx):
    out = run_tool(ctx, "get_match_details", {"club_a": "Coventry", "club_b": "Arsenal"})
    assert out["match"]["match_id"] == 2645195  # the played meeting, not the fixture
    assert [(g["minute"], g["type"]) for g in out["goals"]] == [("15", "Goal"), ("49", "Penalty")]
    assert out["cards"][0]["club"] == "Coventry City" and len(out["substitutions"]) == 1


def test_top_scorers_player_stats_and_compare(ctx):
    top = run_tool(ctx, "get_top_scorers", {"stat": "assists"})
    assert top["players"][0]["player_name"] == "Kai Havertz" and top["players"][0]["assists"] == 2
    assert "error" in run_tool(ctx, "get_top_scorers", {"stat": "tackles"})
    stats = run_tool(ctx, "get_player_stats", {"name": "havertz"})
    assert stats["season_stats"]["goals"] == 1 and stats["season_stats"]["minutes"] == 90
    kepa = run_tool(ctx, "get_player_stats", {"name": "Kepa"})
    assert kepa["club"] == "Arsenal" and kepa["season_stats"] is None
    both = run_tool(ctx, "compare_players", {"names": ["Havertz", "Kepa"]})
    assert [p["player"] for p in both["players"]] == ["Kai Havertz", "Kepa Arrizabalaga"]


def test_club_info_and_head_to_head(ctx):
    info = run_tool(ctx, "get_club_info", {"club": "Arsenal"})
    assert info["stadium"] == "Emirates Stadium" and info["table"]["position"] == 1
    assert info["form_last5_oldest_first"]["form"] == "W" and info["squad_size"] == 1
    assert info["next_fixture"]["home_club"] == "Coventry City"
    assert (
        len(run_tool(ctx, "get_head_to_head", {"club_a": "ARS", "club_b": "COV"})["matches"]) == 2
    )


def test_search_news_filters_and_records_sources(ctx):
    out = run_tool(ctx, "search_news", {"query": "Arsenal beat Coventry"})
    assert [r["source_id"] for r in out["results"]] == ["a4764661"]  # fantasy excluded by default
    assert out["results"][0]["source_id"] == "a4764661" and "url" not in out["results"][0]
    assert ctx.sources[0]["title"] == "Arsenal 3-0 Coventry"
    with_fpl = run_tool(ctx, "search_news", {"query": "FPL price changes", "include_fantasy": True})
    assert "a2884829" in [r["source_id"] for r in with_fpl["results"]]
    by_club = run_tool(ctx, "search_news", {"query": "Arsenal", "club": "Arsenal"})
    assert [r["source_id"] for r in by_club["results"]] == ["a4764661"]
    assert run_tool(ctx, "search_news", {"query": "Arsenal", "club": "Coventry"})["results"] == []
    old = run_tool(ctx, "search_news", {"query": "Arsenal", "days": 1})  # both are older
    assert old["results"] == [] and old["note"]


def test_search_news_fails_closed(ctx):
    ctx.shield = lambda chunks, q: ShieldResult(error="Prompt Shields unavailable")
    out = run_tool(ctx, "search_news", {"query": "Arsenal"})
    assert out["results"] == [] and "unavailable" in out["error"]
    assert ctx.sources == []


def test_build_index_only_reembeds_changed_articles(ctx):
    assert build_index(ctx.conn, ctx.provider)["articles_indexed"] == 0
    ctx.conn.execute("UPDATE silver.articles SET body_text = 'new text' WHERE content_id = 4764661")
    assert build_index(ctx.conn, ctx.provider)["articles_indexed"] == 1


def test_match_lineup_with_events(ctx):
    from ingestion import sample_payloads as s
    from ingestion.__main__ import bronze_sink

    bronze_sink(ctx.conn)("sdp", "v3/matches/2645195/lineups", {}, s.LINEUPS)
    load_from_bronze(ctx.conn)
    out = run_tool(ctx, "get_match_lineup", {"club": "Arsenal", "opponent": "Coventry"})
    (arsenal,) = out["teams"]  # Coventry's side was not published in the sample
    assert (arsenal["club"], arsenal["formation"], arsenal["manager"]) == (
        "Arsenal", "1-1", "Mikel Arteta",
    )  # fmt: skip
    gk, fwd = arsenal["starting_xi_gk_to_attack"]
    assert gk["name"] == "David Raya" and fwd["captain"] and fwd["goals"] == ["15' Goal"]
    (sub,) = arsenal["substitutes"]
    assert (sub["name"], sub["came_on"]) == ("Max Dowman", "68")


def test_match_lineup_not_announced_fetches_on_demand(ctx):
    from ingestion import sample_payloads as s
    from ingestion.silver import load_row

    fetched = []

    def fake_fetch(match_id):
        fetched.append(match_id)
        load_row(ctx.conn, f"v3/matches/{match_id}/lineups", s.LINEUPS_NOT_ANNOUNCED, ctx.now)

    ctx.fetch_lineups = fake_fetch
    out = run_tool(ctx, "get_match_lineup", {"match_id": 2645302})  # the PreMatch fixture
    assert fetched == [2645302] and out["lineup_announced"] is False and "predicted" in out["note"]
