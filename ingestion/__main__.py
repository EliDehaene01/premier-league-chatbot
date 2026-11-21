"""python -m ingestion {backfill,matchweek,news,rebuild}: API -> bronze -> silver, then checks."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from backend.config import settings
from backend.db import get_connection, init_db
from ingestion import quality
from ingestion.pl_client import LEADERBOARD_SORTS, PLClient
from ingestion.silver import load_from_bronze

SILVER_TABLES = ["clubs", "players", "matches", "match_events", "standings_snapshots",
                 "player_season_stats", "articles"]  # fmt: skip


def bronze_sink(conn):
    def sink(source: str, endpoint: str, params: dict, payload) -> None:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        conn.execute(
            "INSERT INTO bronze.api_responses (source, endpoint, params, payload, payload_sha256) "
            "VALUES (%s, %s, %s, %s::jsonb, %s)",
            (source, endpoint, Jsonb(params), body, hashlib.sha256(body.encode()).hexdigest()),
        )

    return sink


def latest_finished_matchweek(matches: list[dict]) -> int | None:
    by_mw: dict[int, list[bool]] = {}
    for m in matches:
        by_mw.setdefault(int(m["matchWeek"]), []).append(m.get("period") == "FullTime")
    # ponytail: a postponed match keeps its matchweek "unfinished"; its events are still caught
    # up because every finished match without events is fetched below.
    done = [mw for mw, finished in by_mw.items() if all(finished)]
    return max(done) if done else None


def fetch_stats(client: PLClient, conn, season: int, all_events: bool) -> dict:
    teams = client.get_teams(season)
    for t in teams:
        client.get_squad(season, t["id"])
    matches = client.get_matches(season)
    client.get_standings(season)
    for sort in LEADERBOARD_SORTS:
        client.get_leaderboard(season, sort)

    mw = latest_finished_matchweek(matches)
    finished = {int(m["matchId"]) for m in matches if m.get("period") == "FullTime"}
    have = {r[0] for r in conn.execute("SELECT DISTINCT match_id FROM silver.match_events")}
    latest = {int(m["matchId"]) for m in matches if int(m["matchWeek"]) == mw} & finished
    todo = finished if all_events else (finished - have) | latest
    for match_id in sorted(todo):
        client.get_match_events(match_id)
    return {"latest_finished_matchweek": mw, "events_fetched": len(todo)}


def article_cutoff(conn) -> datetime:
    last = conn.execute("SELECT max(published_at) FROM silver.articles").fetchone()[0]
    return last - timedelta(days=1) if last else datetime.now(UTC) - timedelta(days=7)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ingestion")
    ap.add_argument("mode", choices=["backfill", "matchweek", "news", "rebuild"])
    ap.add_argument("--season", type=int, default=settings.pl_season)
    ap.add_argument("--since", default="2026-08-01", help="backfill: articles since this date")
    ap.add_argument("--summary", help="write a JSON summary to this path")
    args = ap.parse_args(argv)

    conn = get_connection()
    init_db(conn)
    start_id = conn.execute("SELECT coalesce(max(id), 0) FROM bronze.api_responses").fetchone()[0]
    client = PLClient(on_response=bronze_sink(conn))
    summary: dict = {"mode": args.mode, "season": args.season,
                     "started_at": datetime.now(UTC).isoformat()}  # fmt: skip

    if args.mode in ("backfill", "matchweek"):
        summary |= fetch_stats(client, conn, args.season, all_events=args.mode == "backfill")
    if args.mode in ("backfill", "matchweek", "news"):
        cutoff = (
            datetime.fromisoformat(args.since).replace(tzinfo=UTC)
            if args.mode == "backfill"
            else article_cutoff(conn)
        )
        summary["articles_since"] = cutoff.isoformat()
        summary["articles_fetched"] = len(client.get_articles_since(cutoff))

    summary["bronze_rows_replayed"] = load_from_bronze(
        conn, 0 if args.mode == "rebuild" else start_id
    )
    summary["silver_counts"] = {
        t: conn.execute(f"SELECT count(*) FROM silver.{t}").fetchone()[0] for t in SILVER_TABLES
    }
    checks = quality.ARTICLE_CHECKS if args.mode == "news" else None
    code = 0
    try:
        summary["quality"] = {k: "ok" for k in quality.run(conn, args.season, checks)}
    except quality.QualityError as e:
        summary["quality"] = {"error": str(e)}
        code = 1
    out = json.dumps(summary, indent=2, default=str)
    print(out)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            f.write(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
