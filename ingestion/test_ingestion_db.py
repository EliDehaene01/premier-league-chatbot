"""End-to-end through Postgres: bronze -> silver -> gold, quality, idempotency. Marked db."""

import json
from functools import partial

import httpx
import psycopg
import pytest
import respx

from backend.config import settings
from backend.db import init_db
from ingestion import quality
from ingestion import sample_payloads as s
from ingestion.__main__ import bronze_sink, main
from ingestion.pl_client import CONTENT_API, SDP_API, PLClient
from ingestion.silver import load_from_bronze

pytestmark = pytest.mark.db
S = "v1/competitions/8/seasons/2026"


def fill_bronze(conn):
    sink = bronze_sink(conn)
    sink("sdp", f"{S}/teams", {}, s.TEAMS)
    sink("sdp", f"{S}/teams/3/squad", {}, s.SQUAD)
    sink("sdp", "v2/matches", {"competition": 8}, s.MATCHES)
    sink("sdp", "v1/matches/2645195/events", {}, s.EVENTS)
    sink("sdp", "v5/competitions/8/seasons/2026/standings", {}, s.STANDINGS)
    sink("sdp", f"{S}/players/stats/leaderboard", {"_sort": "goals:desc"}, s.LEADERBOARD_GOALS)
    sink("sdp", f"{S}/players/stats/leaderboard", {"_sort": "x"}, s.LEADERBOARD_ASSISTS)
    sink("content", "content/premierleague/text/EN/", {"page": 0}, s.ARTICLES)


def counts(conn):
    tables = ["clubs", "players", "matches", "match_events", "standings_snapshots",
              "player_season_stats", "articles"]  # fmt: skip
    return {t: conn.execute(f"SELECT count(*) FROM silver.{t}").fetchone()[0] for t in tables}


def test_init_db_is_idempotent(db):
    init_db(db)
    init_db(db)


def test_bronze_is_append_only(db):
    bronze_sink(db)("sdp", "x", {}, {"a": 1})
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("UPDATE bronze.api_responses SET endpoint = 'y'")
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("DELETE FROM bronze.api_responses")


def test_silver_and_gold_from_bronze(db):
    fill_bronze(db)
    assert load_from_bronze(db) == 8
    first = counts(db)
    assert first == {"clubs": 2, "players": 1, "matches": 2, "match_events": 4,
                     "standings_snapshots": 2, "player_season_stats": 1, "articles": 2}  # fmt: skip

    load_from_bronze(db)  # replaying everything again must not duplicate anything
    assert counts(db) == first

    def q(sql):
        return db.execute(sql).fetchall()

    assert q("SELECT position, club, points FROM gold.league_table_current") == [
        (1, "Arsenal", 3), (2, "Coventry City", 0),
    ]  # fmt: skip
    # goals from the goals sort and assists from the assists sort merge into one row
    assert q("SELECT player_name, goals, assists, minutes FROM gold.top_scorers") == [
        ("Kai Havertz", 1, 2, 90)
    ]
    assert q("SELECT player_name, assists FROM gold.top_assists") == [("Kai Havertz", 2)]
    assert q("SELECT club, form, points FROM gold.club_form_last5 ORDER BY club") == [
        ("Arsenal", "W", 3), ("Coventry City", "L", 0),
    ]  # fmt: skip
    assert q("SELECT home_club, home_score, away_score FROM gold.matchweek_results(1)") == [
        ("Arsenal", 3, 0)
    ]
    assert len(q("SELECT * FROM gold.head_to_head(9, 3)")) == 2
    assert q("SELECT * FROM gold.table_moves") == []  # needs two snapshots


def test_table_moves_between_two_snapshots(db):
    fill_bronze(db)
    mw2 = json.loads(json.dumps(s.STANDINGS))
    mw2["matchweek"] = 2
    a, c = mw2["tables"][0]["entries"]
    a["overall"], c["overall"] = {**a["overall"], "position": 2}, {**c["overall"], "position": 1}
    bronze_sink(db)("sdp", "v5/competitions/8/seasons/2026/standings", {}, mw2)
    load_from_bronze(db)
    assert db.execute(
        "SELECT club, from_position, to_position, places_gained FROM gold.table_moves"
    ).fetchall() == [("Coventry City", 2, 1, 1), ("Arsenal", 1, 2, -1)]


def test_quality_checks_fail_loudly(db):
    fill_bronze(db)
    load_from_bronze(db)
    assert quality.run(db, 2026, quality.ARTICLE_CHECKS)
    with pytest.raises(quality.QualityError, match="expected 20 clubs, found 2"):
        quality.run(db, 2026)
    db.execute("UPDATE silver.standings_snapshots SET points = 99 WHERE club_id = 3")
    with pytest.raises(quality.QualityError, match="check_table_arithmetic"):
        quality.run(db, 2026, [quality.check_table_arithmetic])


@respx.mock
def test_cli_news_twice_adds_bronze_but_no_duplicate_articles(db, db_url, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_url", db_url)
    monkeypatch.setattr("ingestion.__main__.PLClient", partial(PLClient, delay=0, backoff=0))
    respx.get(CONTENT_API).mock(
        side_effect=lambda req: httpx.Response(
            200, json=s.ARTICLES if req.url.params["page"] == "0" else {"content": []}
        )
    )
    sdp = respx.get(url__startswith=SDP_API).respond(404)

    summary = tmp_path / "s.json"
    assert main(["news", "--summary", str(summary)]) == 0  # empty db: 7-day cutoff, 1 page
    assert main(["news"]) == 0  # cutoff = newest article - 1 day: page 0, then empty page 1
    assert json.loads(summary.read_text())["silver_counts"]["articles"] == 2
    assert counts(db)["articles"] == 2
    assert db.execute("SELECT count(*) FROM bronze.api_responses").fetchone()[0] == 3
    assert not sdp.called  # news mode never touches the stats API
