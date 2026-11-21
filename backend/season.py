"""Where the season stands: which matchweek is complete. Shared by the chat tools, the system
prompt and the matchweek recap, so they never disagree."""

from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row


def _rows(conn: psycopg.Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def latest_complete_matchweek(conn, now: datetime, pending_after_days: int = 4) -> int | None:
    """The newest matchweek whose fixtures are all played, apart from ones postponed well past it.

    A matchweek still has games to come when an unfinished fixture kicks off within
    `pending_after_days` of its last played game; later ones count as postponed (pending).
    """
    weeks = _rows(
        conn,
        """
        SELECT matchweek,
               count(*) FILTER (WHERE is_finished) AS played,
               max(kickoff_utc) FILTER (WHERE is_finished) AS last_played,
               array_agg(kickoff_utc) FILTER (WHERE NOT is_finished) AS open_kickoffs
        FROM silver.matches
        WHERE season = (SELECT max(season) FROM silver.matches)
        GROUP BY matchweek HAVING count(*) FILTER (WHERE is_finished) > 0
        ORDER BY matchweek DESC""",
    )
    for w in weeks:
        limit = w["last_played"] + timedelta(days=pending_after_days)
        still_to_play = [k for k in w["open_kickoffs"] or [] if k is None or k <= limit]
        # a kickoff in the past that is not finished is live or awaiting its result
        if not still_to_play and w["last_played"] <= now:
            return w["matchweek"]
    return None
