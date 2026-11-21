"""Data-quality checks on silver. Each check returns a list of problems; run() raises on any."""

import psycopg


class QualityError(Exception):
    pass


def _rows(conn: psycopg.Connection, sql: str, params=()) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


def check_club_count(conn, season):
    n = _rows(conn, "SELECT count(*) FROM silver.clubs")[0][0]
    return [] if n == 20 else [f"expected 20 clubs, found {n}"]


def check_match_count(conn, season):
    n = _rows(conn, "SELECT count(*) FROM silver.matches WHERE season = %s", (season,))[0][0]
    return [] if n == 380 else [f"expected 380 matches in season {season}, found {n}"]


def check_table_arithmetic(conn, season):
    # ponytail: assumes no points deductions (the API's `deductions` list is empty in 2026-27)
    bad = _rows(
        conn,
        "SELECT matchweek, club_id, points, won, drawn, lost, played "
        "FROM silver.standings_snapshots WHERE season = %s "
        "AND (points <> 3 * won + drawn OR played <> won + drawn + lost)",
        (season,),
    )
    return [f"mw{r[0]} club {r[1]} (pts, W, D, L, P) = {r[2:]}" for r in bad]


def check_finished_have_scores(conn, season):
    bad = _rows(
        conn,
        "SELECT match_id FROM silver.matches WHERE season = %s AND is_finished "
        "AND (home_score IS NULL OR away_score IS NULL)",
        (season,),
    )
    return [f"finished match {r[0]} has no score" for r in bad]


def check_article_ids_unique(conn, season):
    dup = _rows(conn, "SELECT content_id FROM silver.articles GROUP BY 1 HAVING count(*) > 1")
    return [f"duplicate article id {r[0]}" for r in dup]


STATS_CHECKS = [check_club_count, check_match_count, check_table_arithmetic,
                check_finished_have_scores]  # fmt: skip
ARTICLE_CHECKS = [check_article_ids_unique]


def run(conn: psycopg.Connection, season: int, checks=None) -> dict[str, list[str]]:
    """Run checks; return {check name: problems}. Raises QualityError if any check found one."""
    results = {c.__name__: c(conn, season) for c in (checks or STATS_CHECKS + ARTICLE_CHECKS)}
    failed = {k: v for k, v in results.items() if v}
    if failed:
        raise QualityError("; ".join(f"{k}: {', '.join(v[:5])}" for k, v in failed.items()))
    return results
