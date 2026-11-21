"""Facts for the Tuesday matchweek recap, gathered by code from silver and gold.

Every fact carries the source_id the model must cite: m<matchId> for a match, t<matchweek> for
the table, s<date> for the player stats snapshot.
"""

from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import dict_row

from backend.season import latest_complete_matchweek

POINTS = {"W": 3, "D": 1, "L": 0}


def _rows(conn: psycopg.Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _scorers(conn, match_ids: list[int]) -> dict[int, list[dict]]:
    rows = _rows(
        conn,
        """
        SELECT e.match_id, e.club_id, c.name AS club, e.detail, e.minute,
               coalesce(p.name, 'Unknown') AS player, a.name AS assist
        FROM silver.match_events e
        JOIN silver.clubs c ON c.club_id = e.club_id
        LEFT JOIN silver.players p ON p.player_id = e.player_id
        LEFT JOIN silver.players a ON a.player_id = e.secondary_player_id
        WHERE e.event_type = 'goal' AND e.match_id = ANY(%s)
        ORDER BY e.match_id, e.seq""",
        (match_ids,),
    )
    out: dict[int, list[dict]] = {}
    for r in rows:
        goal = {"club": r["club"], "player": r["player"], "minute": r["minute"]}
        if r["detail"] and r["detail"] != "Goal":
            goal["type"] = r["detail"]  # Penalty, OwnGoal
        if r["assist"] and r["detail"] != "OwnGoal":
            goal["assist"] = r["assist"]
        out.setdefault(r["match_id"], []).append(goal)
    return out


def _red_cards(conn, match_ids: list[int]) -> dict[int, list[dict]]:
    rows = _rows(
        conn,
        """
        SELECT e.match_id, c.name AS club, coalesce(p.name, 'Unknown') AS player, e.minute
        FROM silver.match_events e
        JOIN silver.clubs c ON c.club_id = e.club_id
        LEFT JOIN silver.players p ON p.player_id = e.player_id
        WHERE e.event_type = 'card' AND e.detail ILIKE '%%red%%' AND e.match_id = ANY(%s)
        ORDER BY e.match_id, e.seq""",
        (match_ids,),
    )
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["match_id"], []).append(
            {"club": r["club"], "player": r["player"], "minute": r["minute"]}
        )
    return out


def standings(matches: list[dict], clubs: dict[int, str]) -> list[dict]:
    """A league table from finished matches: points, then goal difference, then goals scored.

    Head-to-head and play-off tie-breakers are left out; they only matter on exact ties.
    """
    t = {
        cid: {
            "club_id": cid,
            "club": name,
            "played": 0,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "points": 0,
        }
        for cid, name in clubs.items()
    }
    for m in matches:
        for side, gf, ga in (
            ("home", m["home_score"], m["away_score"]),
            ("away", m["away_score"], m["home_score"]),
        ):
            row = t[m[f"{side}_club_id"]]
            result = "W" if gf > ga else "D" if gf == ga else "L"
            row["played"] += 1
            row[{"W": "won", "D": "drawn", "L": "lost"}[result]] += 1
            row["goals_for"] += gf
            row["goals_against"] += ga
            row["points"] += POINTS[result]
    rows = sorted(
        t.values(),
        key=lambda r: (
            -r["points"],
            -(r["goals_for"] - r["goals_against"]),
            -r["goals_for"],
            r["club"],
        ),
    )
    for i, r in enumerate(rows, 1):
        r["position"] = i
        r["goal_difference"] = r["goals_for"] - r["goals_against"]
    return rows


def gather(
    conn: psycopg.Connection,
    matchweek: int | None = None,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> dict:
    """Everything the recap may say about one matchweek, or {"error": ...}."""
    cfg = cfg or {}
    now = now or datetime.now(UTC)
    mw = matchweek or latest_complete_matchweek(conn, now, cfg.get("pending_after_days", 4))
    if mw is None:
        return {"error": "no completed matchweek yet"}
    season = conn.execute("SELECT max(season) FROM silver.matches").fetchone()[0]
    week = _rows(
        conn,
        "SELECT * FROM gold.match_results WHERE season = %s AND matchweek = %s "
        "ORDER BY kickoff_utc, match_id",
        (season, mw),
    )
    played = [m for m in week if m["period"] == "FullTime"]
    if not played:
        return {"error": f"matchweek {mw} has no finished matches"}
    first, last = min(m["kickoff_utc"] for m in played), max(m["kickoff_utc"] for m in played)
    # catch-ups: earlier-matchweek games played well after their own matchweek (postponed),
    # since the previous matchweek's regular games and up to the end of this one
    pending_days = timedelta(days=cfg.get("pending_after_days", 4))
    earlier = _rows(
        conn,
        "SELECT * FROM gold.match_results WHERE season = %s AND matchweek < %s "
        "AND period = 'FullTime' AND kickoff_utc <= %s ORDER BY kickoff_utc",
        (season, mw, last),
    )
    regular_end = {}  # matchweek -> when its regular games were over
    for m in earlier:
        regular_end.setdefault(m["matchweek"], []).append(m["kickoff_utc"])
    regular_end = {k: sorted(v)[len(v) // 2] + pending_days for k, v in regular_end.items()}
    since = regular_end.get(mw - 1, first - pending_days)
    catch_up = [
        m
        for m in earlier
        if m["kickoff_utc"] > regular_end[m["matchweek"]] and m["kickoff_utc"] > since
    ]
    ids = [m["match_id"] for m in played + catch_up]
    scorers, reds = _scorers(conn, ids), _red_cards(conn, ids)

    def match_fact(m: dict) -> dict:
        f = {
            "source_id": f"m{m['match_id']}",
            "matchweek": m["matchweek"],
            "kickoff_utc": m["kickoff_utc"].isoformat(),
            "home": m["home_club"],
            "away": m["away_club"],
            "score": f"{m['home_score']}-{m['away_score']}",
            "half_time": f"{m['home_ht_score']}-{m['away_ht_score']}",
            "ground": m["ground"],
            "goals": scorers.get(m["match_id"], []),
        }
        if reds.get(m["match_id"]):
            f["red_cards"] = reds[m["match_id"]]
        if m["home_ht_score"] is not None:  # a side behind at half-time that went on to win
            ht, ft = m["home_ht_score"] - m["away_ht_score"], m["home_score"] - m["away_score"]
            if ht * ft < 0:
                f["comeback_by"] = m["home_club"] if ft > 0 else m["away_club"]
        return f

    results = [match_fact(m) for m in played]
    pending = [
        {
            "source_id": f"m{m['match_id']}",
            "home": m["home_club"],
            "away": m["away_club"],
            "kickoff_utc": m["kickoff_utc"].isoformat() if m["kickoff_utc"] else None,
        }
        for m in week
        if m["period"] != "FullTime"
    ]

    # table before and after, from results, so moves work with a single standings snapshot
    clubs = dict(
        conn.execute(
            "SELECT club_id, name FROM silver.clubs WHERE club_id IN "
            "(SELECT home_club_id FROM silver.matches WHERE season = %s)",
            (season,),
        ).fetchall()
    )
    finished = _rows(
        conn,
        "SELECT home_club_id, away_club_id, home_score, away_score, kickoff_utc "
        "FROM silver.matches WHERE season = %s AND is_finished",
        (season,),
    )
    before = standings([m for m in finished if m["kickoff_utc"] < first], clubs)
    after = standings([m for m in finished if m["kickoff_utc"] <= last], clubs)
    pos_before = {r["club_id"]: r["position"] for r in before}
    table = [
        {
            "position": r["position"],
            "club": r["club"],
            "played": r["played"],
            "won": r["won"],
            "drawn": r["drawn"],
            "lost": r["lost"],
            "goal_difference": r["goal_difference"],
            "points": r["points"],
            "previous_position": pos_before[r["club_id"]],
            "places_gained": pos_before[r["club_id"]] - r["position"],
        }
        for r in after
    ]
    top4 = lambda rows: {r["club"] for r in rows if r["position"] <= 4}  # noqa: E731
    bottom3 = lambda rows: {r["club"] for r in rows if r["position"] > len(rows) - 3}  # noqa: E731

    # cross-check against the official table when its snapshot is for this matchweek
    official = dict(
        conn.execute(
            "SELECT c.name, s.position FROM silver.standings_snapshots s JOIN silver.clubs c "
            "USING (club_id) WHERE s.season = %s AND s.matchweek = %s",
            (season, mw),
        ).fetchall()
    )
    mismatches = [r["club"] for r in table if official and official.get(r["club"]) != r["position"]]

    # goals per player this matchweek; hat-tricks
    tally: dict[tuple, int] = {}
    for f in results:
        for g in f["goals"]:
            if g.get("type") != "OwnGoal":
                tally[(f["source_id"], g["player"], g["club"])] = (
                    tally.get((f["source_id"], g["player"], g["club"]), 0) + 1
                )
    hat_tricks = [
        {"source_id": sid, "player": p, "club": c, "goals": n}
        for (sid, p, c), n in tally.items()
        if n >= 3
    ]
    clean_sheets = sorted(
        [
            {"source_id": f["source_id"], "club": f["home"]}
            for f in results
            if f["score"].endswith("-0")
        ]
        + [
            {"source_id": f["source_id"], "club": f["away"]}
            for f in results
            if f["score"].startswith("0-")
        ],
        key=lambda x: x["club"],
    )
    margin = lambda f: abs(eval_score(f["score"]))  # noqa: E731
    biggest = max(results, key=lambda f: (margin(f), total_goals(f["score"])))

    snap = conn.execute("SELECT max(snapshot_date) FROM silver.player_season_stats").fetchone()[0]
    scorers_top = _rows(
        conn,
        "SELECT rank, player_name AS player, club, goals FROM gold.top_scorers LIMIT %s",
        (cfg.get("top_scorers", 5),),
    )

    return {
        "season": f"{season}-{(season + 1) % 100:02d}",
        "matchweek": mw,
        "period_start": first.isoformat(),
        "period_end": last.isoformat(),
        "results": results,
        "catch_up_results": [match_fact(m) for m in catch_up],
        "pending_fixtures": pending,
        "table": {
            "source_id": f"t{mw}",
            "after_matchweek": mw,
            "rows": table,
            "entered_top4": sorted(top4(after) - top4(before)),
            "left_top4": sorted(top4(before) - top4(after)),
            "entered_bottom3": sorted(bottom3(after) - bottom3(before)),
            "left_bottom3": sorted(bottom3(before) - bottom3(after)),
        },
        "highlights": {
            "biggest_win": biggest["source_id"],
            "hat_tricks": hat_tricks,
            "clean_sheets": clean_sheets,
            "comebacks": [
                {"source_id": f["source_id"], "club": f["comeback_by"]}
                for f in results
                if "comeback_by" in f
            ],
            "total_goals": sum(total_goals(f["score"]) for f in results),
        },
        "top_scorers": {
            "source_id": f"s{snap}" if snap else None,
            "as_of": str(snap),
            "players": scorers_top,
        },
        "checks": {
            "table_matches_official": not mismatches if official else None,
            "table_mismatches": mismatches,
        },
    }


def eval_score(score: str) -> int:
    h, a = score.split("-")
    return int(h) - int(a)


def total_goals(score: str) -> int:
    h, a = score.split("-")
    return int(h) + int(a)
