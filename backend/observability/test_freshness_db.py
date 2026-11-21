"""Freshness checks on the sample payloads. Marked db."""

from datetime import timedelta

import pytest

from backend.observability import freshness
from ingestion.silver import load_from_bronze
from ingestion.test_ingestion_db import fill_bronze

pytestmark = pytest.mark.db


@pytest.fixture
def conn(db):
    fill_bronze(db)
    load_from_bronze(db)
    return db


def last_fetch(conn):
    return conn.execute("SELECT max(fetched_at) FROM bronze.api_responses").fetchone()[0]


def by_name(checks):
    return {c.name: c for c in checks}


def test_right_after_ingestion(conn):
    checks = by_name(freshness.run_checks(conn, last_fetch(conn) + timedelta(hours=1)))
    assert checks["ingestion"].status == "ok"
    assert checks["results"].status == "ok"
    assert set(checks) == {f.__name__ for f in freshness.CHECKS}


def test_ingestion_goes_stale_then_fails(conn):
    at = last_fetch(conn)
    assert by_name(freshness.run_checks(conn, at + timedelta(days=5)))["ingestion"].status == "warn"
    checks = freshness.run_checks(conn, at + timedelta(days=9))
    assert by_name(checks)["ingestion"].status == "fail"
    assert freshness.worst(checks) == "fail"


def test_missing_result_fails(conn):
    conn.execute(
        "INSERT INTO silver.matches (match_id, season, matchweek, kickoff_utc, home_club_id, "
        "away_club_id, period) SELECT 1, season, matchweek, %s, away_club_id, home_club_id, "
        "'SecondHalf' FROM silver.matches LIMIT 1",
        (last_fetch(conn) - timedelta(hours=5),),
    )
    check = by_name(freshness.run_checks(conn, last_fetch(conn)))["results"]
    assert check.status == "fail" and check.data["match_ids"] == [1]


def test_store_keeps_history(conn):
    freshness.store(conn, freshness.run_checks(conn))
    n = conn.execute("SELECT count(DISTINCT name) FROM public.freshness_checks").fetchone()[0]
    assert n == len(freshness.CHECKS)
