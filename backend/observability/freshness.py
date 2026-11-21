"""Data freshness checks: is what the chatbot answers from up to date?

Each check returns ok, warn or fail with the numbers behind it. The API's /api/health shows
them (the UI badge turns amber or red), the scheduled ingestion runs them afterwards with
--store (a history for the AI Ops dashboard) and exits non-zero on a failure, so a broken
run shows up in Task Scheduler instead of as quietly stale answers.

    python -m backend.observability.freshness [--store] [--json]
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.season import latest_complete_matchweek

# ingestion runs twice a week (Mon and Thu nights), so the longest normal gap is about 4 days
INGEST_WARN, INGEST_FAIL = timedelta(days=4, hours=6), timedelta(days=8)
NEWS_WARN, NEWS_FAIL = timedelta(days=4), timedelta(days=8)
RESULT_GRACE = timedelta(hours=3)  # a match kicked off this long before a fetch has a result
DIGEST_GRACE = timedelta(days=2)  # the Tuesday recap follows Monday night's ingestion
ORDER = {"ok": 0, "warn": 1, "fail": 2}


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail
    detail: str
    data: dict = field(default_factory=dict)


def _one(conn, sql: str, params=()) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def _age(now: datetime, then: datetime | None) -> str:
    if then is None:
        return "never"
    hours = (now - then).total_seconds() / 3600
    return f"{hours:.0f} hours ago" if hours < 48 else f"{hours / 24:.1f} days ago"


def ingestion(conn, now: datetime) -> Check:
    last = _one(conn, "SELECT max(fetched_at) AS t FROM bronze.api_responses")["t"]
    status = (
        "fail"
        if last is None or now - last > INGEST_FAIL
        else "warn"
        if now - last > INGEST_WARN
        else "ok"
    )
    return Check("ingestion", status, f"last fetch {_age(now, last)}", {"last_fetch": last})


def results(conn, now: datetime) -> Check:
    """Matches that had kicked off well before the last fetch but still have no result."""
    row = _one(
        conn,
        "SELECT count(*) AS missing, array_agg(match_id ORDER BY kickoff_utc) AS ids "
        "FROM silver.matches WHERE NOT is_finished AND kickoff_utc < "
        "(SELECT max(fetched_at) FROM bronze.api_responses) - %s",
        (RESULT_GRACE,),
    )
    n = row["missing"]
    detail = "every match played before the last fetch has a result"
    if n:
        detail = f"{n} match(es) played before the last fetch have no final result"
    return Check("results", "fail" if n else "ok", detail, {"match_ids": (row["ids"] or [])[:10]})


def table(conn, now: datetime) -> Check:
    row = _one(
        conn,
        "SELECT (SELECT max(fetched_at) FROM silver.standings_snapshots) AS table_at, "
        "(SELECT max(kickoff_utc) FROM silver.matches WHERE is_finished) AS last_result",
    )
    stale = row["table_at"] is None or (
        row["last_result"] is not None and row["table_at"] < row["last_result"] + RESULT_GRACE
    )
    detail = "older than the latest result" if stale else f"fetched {_age(now, row['table_at'])}"
    return Check("table", "warn" if stale else "ok", f"league table {detail}", row)


def news(conn, now: datetime) -> Check:
    last = _one(conn, "SELECT max(published_at) AS t FROM silver.articles")["t"]
    status = (
        "fail"
        if last is None or now - last > NEWS_FAIL
        else "warn"
        if now - last > NEWS_WARN
        else "ok"
    )
    return Check("news", status, f"newest article {_age(now, last)}", {"newest_article": last})


def index(conn, now: datetime) -> Check:
    """Articles with text from the last 30 days that the news search cannot find yet."""
    row = _one(
        conn,
        "SELECT count(*) AS unindexed FROM silver.articles a WHERE coalesce(a.body_text, '') "
        "<> '' AND a.published_at > %s AND NOT EXISTS (SELECT 1 FROM silver.article_chunks c "
        "WHERE c.content_id = a.content_id)",
        (now - timedelta(days=30),),
    )
    n = row["unindexed"]
    detail = f"{n} recent article(s) not in the news index" if n else "news index up to date"
    return Check("index", "warn" if n else "ok", detail, row)


def digests(conn, now: datetime) -> Check:
    rows = {
        r["kind"]: r
        for r in conn.cursor(row_factory=dict_row).execute(
            "SELECT DISTINCT ON (kind) kind, period_key, created_at FROM public.digests "
            "ORDER BY kind, created_at DESC"
        )
    }
    problems = []
    completed = latest_complete_matchweek(conn, now)
    recap = rows.get("matchweek_recap")
    if completed and (recap is None or recap["period_key"] != f"mw{completed}"):
        done_at = _one(
            conn,
            "SELECT max(kickoff_utc) AS t FROM silver.matches WHERE matchweek = %s",
            (completed,),
        )["t"]
        if done_at and now - done_at > DIGEST_GRACE:
            problems.append(f"no recap for matchweek {completed} yet")
    highlights = rows.get("news_highlights")
    if highlights is None or now - highlights["created_at"] > timedelta(days=8):
        problems.append("no news highlights in the last 8 days")
    return Check(
        "digests",
        "warn" if problems else "ok",
        "; ".join(problems) or "weekly digests up to date",
        {k: v["period_key"] for k, v in rows.items()},
    )


CHECKS = (ingestion, results, table, news, index, digests)


def run_checks(conn: psycopg.Connection, now: datetime | None = None) -> list[Check]:
    now = now or datetime.now(UTC)
    out = []
    for check in CHECKS:
        try:
            out.append(check(conn, now))
        except psycopg.Error as e:  # one broken check must not hide the others
            conn.rollback()
            out.append(Check(check.__name__, "fail", f"check failed: {type(e).__name__}"))
    return out


def worst(checks: list[Check]) -> str:
    return max((c.status for c in checks), key=ORDER.__getitem__, default="ok")


def store(conn: psycopg.Connection, checks: list[Check]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO public.freshness_checks (name, status, detail, data) "
            "VALUES (%s, %s, %s, %s)",
            [
                (c.name, c.status, c.detail, Jsonb(json.loads(json.dumps(c.data, default=str))))
                for c in checks
            ],
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.observability.freshness")
    ap.add_argument("--store", action="store_true", help="keep the result for the dashboard")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    from backend.db import get_connection, init_db

    conn = get_connection()
    init_db(conn)
    checks = run_checks(conn)
    if args.store:
        store(conn, checks)
    if args.json:
        print(json.dumps([asdict(c) for c in checks], default=str, indent=1))
    else:
        for c in checks:
            print(f"{c.status.upper():<5} {c.name:<10} {c.detail}")
    return 1 if worst(checks) == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
