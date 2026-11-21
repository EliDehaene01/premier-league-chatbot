"""Chat tools: plain functions over gold/silver returning plain dicts, plus their JSON schemas.

Every tool takes a ToolContext first; the model supplies the remaining keyword arguments.
Errors the model should see (unknown or ambiguous names, missing data) are returned as
{"error": ...} rather than raised.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.llm.providers import LLMProvider
from backend.rag import retrieval, shields
from backend.season import latest_complete_matchweek
from backend.tools.resolver import resolve_club, resolve_player

STATS = ("goals", "assists", "clean_sheets")
PLAYER_EXTRAS = ("totalShots", "shotsOnTargetIncGoals", "penaltyGoals", "headedGoals",
                 "keyPassesAttemptAssists", "bigChancesCreated", "totalPasses", "touches",
                 "tacklesWon", "interceptions", "savesMade", "goalsConceded")  # fmt: skip


@dataclass
class ToolContext:
    conn: psycopg.Connection
    provider: LLMProvider
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    shield: Any = shields.shield  # swapped in tests
    sources: list[dict] = field(default_factory=list)  # articles returned by search_news
    fetch_lineups: Any = None  # match_id -> None; fetches into bronze/silver (None = live API)
    tools: Any = None  # an MCP client (mcp_server.client.McpTools); None = call the tools directly


def _rows(ctx: ToolContext, sql: str, params=()) -> list[dict]:
    with ctx.conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _club_id(ctx, name):
    if not name:
        return None, None
    r = resolve_club(ctx.conn, name)
    return (r.match["id"], None) if r.match else (None, r.error("club", name))


MATCH_COLS = (
    "match_id, matchweek, kickoff_utc, home_club, away_club, home_score, away_score, "
    "home_ht_score, away_ht_score, period, ground"
)


def _match(row: dict) -> dict:
    out = {k: v for k, v in row.items() if v is not None}
    if isinstance(out.get("kickoff_utc"), datetime):
        out["kickoff_utc"] = out["kickoff_utc"].isoformat()
    if "match_id" in out:
        out["source_id"] = f"m{out['match_id']}"  # cite as [m<id>]; see backend/llm/citations.py
    return out


def get_league_table(ctx: ToolContext, as_of_matchweek: int | None = None) -> dict:
    snaps = [r["matchweek"] for r in _rows(ctx, "SELECT DISTINCT matchweek FROM "
                                              "silver.standings_snapshots ORDER BY 1")]  # fmt: skip
    if not snaps:
        return {"error": "no standings stored yet"}
    mw = as_of_matchweek or snaps[-1]
    if mw not in snaps:
        return {"error": f"no table stored for matchweek {mw}", "available_matchweeks": snaps}
    table = _rows(
        ctx,
        "SELECT s.position, c.name AS club, s.played, s.won, s.drawn, s.lost, s.goals_for, "
        "s.goals_against, s.goals_for - s.goals_against AS goal_difference, s.points "
        "FROM silver.standings_snapshots s JOIN silver.clubs c USING (club_id) "
        "WHERE s.matchweek = %s ORDER BY s.position",
        (mw,),
    )
    return {**_table_label(ctx, mw), "source_id": f"t{mw}", "table": table}


def _table_label(ctx: ToolContext, mw: int) -> dict:
    """The official table is stored under the matchweek that was active when it was fetched,
    which may be only partly played: say which matchweek it is complete after, and what of
    the next one it already includes."""
    row = _rows(
        ctx,
        "SELECT count(*) AS total, count(*) FILTER (WHERE m.is_finished AND m.kickoff_utc <= "
        "s.fetched) AS played FROM silver.matches m, (SELECT max(fetched_at) AS fetched FROM "
        "silver.standings_snapshots WHERE matchweek = %s) s WHERE m.matchweek = %s "
        "AND m.season = (SELECT max(season) FROM silver.matches)",
        (mw, mw),
    )[0]
    completed = latest_complete_matchweek(ctx.conn, ctx.now)
    if row["played"] == row["total"] or (completed is not None and completed >= mw):
        return {"after_matchweek": mw}
    label = {"after_matchweek": mw - 1, "matchweek_in_progress": mw}
    label["note"] = (
        f"the live table: every game up to matchweek {mw - 1}, plus {row['played']} of the "
        f"{row['total']} matchweek {mw} games played so far"
    )
    return label


def get_fixtures(ctx, club=None, date_from=None, date_to=None, limit: int = 10) -> dict:
    club_id, err = _club_id(ctx, club)
    if err:
        return err
    rows = _rows(
        ctx,
        f"SELECT {MATCH_COLS} FROM gold.match_results WHERE period = 'PreMatch' "
        "AND kickoff_utc >= coalesce(%s::date, %s) AND (%s::date IS NULL OR "
        "kickoff_utc < %s::date + 1) AND (%s::int IS NULL OR %s IN (home_club_id, away_club_id)) "
        "ORDER BY kickoff_utc LIMIT %s",
        (date_from, ctx.now, date_to, date_to, club_id, club_id, min(limit, 50)),
    )
    return {"fixtures": [_match(r) for r in rows], "times": "UTC"}


def get_results(
    ctx, club=None, matchweek: int | None = None, limit: int = 10, oldest_first: bool = False
) -> dict:
    club_id, err = _club_id(ctx, club)
    if err:
        return err
    rows = _rows(
        ctx,
        f"SELECT {MATCH_COLS} FROM gold.match_results WHERE period = 'FullTime' "
        "AND (%s::int IS NULL OR matchweek = %s) "
        "AND (%s::int IS NULL OR %s IN (home_club_id, away_club_id)) "
        f"ORDER BY kickoff_utc {'ASC' if oldest_first else 'DESC'} LIMIT %s",
        (matchweek, matchweek, club_id, club_id, min(limit, 50)),
    )
    return {"results": [_match(r) for r in rows]}


def _find_match(ctx, club_a, club_b=None, date=None) -> tuple[int | None, dict | None]:
    """A club's match: against club_b and/or on a date; else the latest played, else the next."""
    a, err = _club_id(ctx, club_a)
    b, err_b = _club_id(ctx, club_b)
    if err or err_b or a is None:
        return None, err or err_b or {"error": "give match_id, or a club"}
    found = _rows(
        ctx,
        "SELECT match_id FROM gold.match_results WHERE %s IN (home_club_id, away_club_id) "
        "AND (%s::int IS NULL OR %s IN (home_club_id, away_club_id)) "
        "AND (%s::date IS NULL OR kickoff_utc::date = %s::date) "
        "ORDER BY (period = 'FullTime' AND kickoff_utc <= %s) DESC, "
        "abs(extract(epoch FROM kickoff_utc - %s))",
        (a, b, b, date, date, ctx.now, ctx.now),
    )
    if not found:
        return None, {"error": "no matching match found" + (f" on {date}" if date else "")}
    return found[0]["match_id"], None


def get_match_details(ctx, match_id=None, club_a=None, club_b=None, date=None) -> dict:
    if match_id is None:
        if not club_b:
            return {"error": "give match_id, or club_a and club_b"}
        match_id, err = _find_match(ctx, club_a, club_b, date)
        if err:
            return err
    match = _rows(ctx, f"SELECT {MATCH_COLS} FROM gold.match_results WHERE match_id = %s",
                  (match_id,))  # fmt: skip
    if not match:
        return {"error": f"unknown match_id {match_id}"}
    events = _rows(
        ctx,
        "WITH names AS (SELECT player_id, name FROM silver.players UNION "
        "  SELECT player_id, player_name FROM gold.latest_player_stats) "
        "SELECT e.event_type, e.detail, e.minute, c.name AS club, "
        "  (SELECT name FROM names WHERE player_id = e.player_id LIMIT 1) AS player, "
        "  (SELECT name FROM names WHERE player_id = e.secondary_player_id LIMIT 1) AS other "
        "FROM silver.match_events e JOIN silver.clubs c USING (club_id) "
        "WHERE e.match_id = %s ORDER BY e.seq",
        (match_id,),
    )
    goals = [{"minute": e["minute"], "club": e["club"], "scorer": e["player"],
              "assist": e["other"], "type": e["detail"]}
             for e in events if e["event_type"] == "goal"]  # fmt: skip
    cards = [{"minute": e["minute"], "club": e["club"], "player": e["player"], "card": e["detail"]}
             for e in events if e["event_type"] == "card"]  # fmt: skip
    subs = [{"minute": e["minute"], "club": e["club"], "on": e["player"], "off": e["other"]}
            for e in events if e["event_type"] == "sub"]  # fmt: skip
    return {"match": _match(match[0]), "goals": goals, "cards": cards, "substitutions": subs}


def _fetch_lineups_live(ctx, match_id: int) -> None:
    from ingestion.__main__ import bronze_sink  # tools stay importable without ingestion deps
    from ingestion.pl_client import PLClient
    from ingestion.silver import load_row

    payload = PLClient(on_response=bronze_sink(ctx.conn)).get_match_lineups(match_id)
    load_row(ctx.conn, f"v3/matches/{match_id}/lineups", payload, ctx.now)


def get_match_lineup(ctx, match_id=None, club=None, opponent=None, date=None) -> dict:
    if match_id is None:
        match_id, err = _find_match(ctx, club, opponent, date)
        if err:
            return err
    match = _rows(ctx, f"SELECT {MATCH_COLS} FROM gold.match_results WHERE match_id = %s",
                  (match_id,))  # fmt: skip
    if not match:
        return {"error": f"unknown match_id {match_id}"}
    teams_sql = "SELECT club_id, formation, manager FROM silver.match_lineups WHERE match_id = %s"
    teams = _rows(ctx, teams_sql, (match_id,))
    if not teams and match[0]["period"] != "FullTime":  # announced about an hour before kickoff
        (ctx.fetch_lineups or (lambda m: _fetch_lineups_live(ctx, m)))(match_id)
        teams = _rows(ctx, teams_sql, (match_id,))
    if not teams:
        return {"match": _match(match[0]), "lineup_announced": False,
                "note": "line-ups are not published yet (usually about an hour before kick-off);"
                        " search_news can find predicted line-ups"}  # fmt: skip
    players = _rows(
        ctx,
        "SELECT p.club_id, p.player_id, p.name, p.shirt_num, p.position, p.is_captain, "
        "p.is_starter, p.formation_row, p.formation_order FROM silver.match_lineup_players p "
        "WHERE p.match_id = %s ORDER BY p.is_starter DESC, p.formation_row, p.formation_order",
        (match_id,),
    )
    events = _rows(ctx, "SELECT event_type, detail, minute, player_id, secondary_player_id "
                        "FROM silver.match_events WHERE match_id = %s ORDER BY seq",
                   (match_id,))  # fmt: skip
    clubs = {c["club_id"]: c["name"] for c in _rows(ctx, "SELECT club_id, name FROM silver.clubs")}
    out_teams = []
    for t in teams:
        xi, bench = [], []
        for p in (p for p in players if p["club_id"] == t["club_id"]):
            pid = p["player_id"]
            row = {"name": p["name"], "shirt": p["shirt_num"], "position": p["position"]}
            if p["is_starter"]:  # formation row, 1 = goalkeeper; the UI draws the pitch from it
                row["row"] = p["formation_row"]
            if p["is_captain"]:
                row["captain"] = True
            for e in events:
                if e["event_type"] == "goal" and e["player_id"] == pid:
                    row.setdefault("goals", []).append(f"{e['minute']}' {e['detail']}")
                elif e["event_type"] == "goal" and e["secondary_player_id"] == pid:
                    row.setdefault("assists", []).append(f"{e['minute']}'")
                elif e["event_type"] == "card" and e["player_id"] == pid:
                    row.setdefault("cards", []).append(f"{e['minute']}' {e['detail']}")
                elif e["event_type"] == "sub" and e["player_id"] == pid:
                    row["came_on"] = e["minute"]
                elif e["event_type"] == "sub" and e["secondary_player_id"] == pid:
                    row["went_off"] = e["minute"]
            (xi if p["is_starter"] else bench).append(row)
        out_teams.append({"club": clubs.get(t["club_id"]), "formation": t["formation"],
                          "manager": t["manager"], "starting_xi_gk_to_attack": xi,
                          "substitutes": bench})  # fmt: skip
    return {"match": _match(match[0]), "lineup_announced": True, "teams": out_teams}


def get_top_scorers(ctx, limit: int = 10, stat: str = "goals") -> dict:
    if stat not in STATS:
        return {"error": f"stat must be one of {', '.join(STATS)}"}
    rows = _rows(
        ctx,
        f"SELECT rank() OVER (ORDER BY {stat} DESC) AS rank, player_name, club, position, "
        f"{stat}, appearances, minutes, snapshot_date FROM gold.latest_player_stats "
        f"WHERE {stat} > 0 ORDER BY {stat} DESC, minutes LIMIT %s",
        (min(limit, 50),),
    )
    as_of = rows[0]["snapshot_date"].isoformat() if rows else None
    for r in rows:
        r.pop("snapshot_date")
    return {
        "stat": stat,
        "as_of": as_of,
        "source_id": f"s{as_of}" if as_of else None,
        "players": rows,
    }


def get_player_stats(ctx, name: str) -> dict:
    r = resolve_player(ctx.conn, name)
    if not r.match:
        return r.error("player", name)
    pid = r.match["id"]
    rows = _rows(ctx, "SELECT * FROM gold.latest_player_stats WHERE player_id = %s", (pid,))
    bio = _rows(ctx, "SELECT p.position, p.nationality, p.shirt_number, p.birth_date, "
                     "c.name AS club FROM silver.players p LEFT JOIN silver.clubs c "
                     "USING (club_id) WHERE p.player_id = %s", (pid,))  # fmt: skip
    out: dict = {"player": r.match["name"], **(bio[0] if bio else {"club": r.match.get("club")})}
    if not rows:
        out["season_stats"] = None
        out["note"] = "no Premier League stats recorded this season (no appearances yet)"
        return out
    s = rows[0]
    out["as_of"] = s["snapshot_date"].isoformat()
    out["source_id"] = f"s{out['as_of']}"
    out["season_stats"] = {k: s[k] for k in ("appearances", "starts", "minutes", "goals",
                           "assists", "clean_sheets", "yellow_cards", "red_cards")}  # fmt: skip
    out["season_stats"] |= {k: s["stats"][k] for k in PLAYER_EXTRAS if k in s["stats"]}
    return out


def compare_players(ctx, names: list[str]) -> dict:
    return {"players": [get_player_stats(ctx, n) for n in names[:5]]}


def get_club_info(ctx, club: str) -> dict:
    club_id, err = _club_id(ctx, club)
    if err:
        return err
    info = _rows(ctx, "SELECT name, short_name, stadium, city, capacity FROM silver.clubs "
                      "WHERE club_id = %s", (club_id,))[0]  # fmt: skip
    standing = _rows(
        ctx,
        "SELECT position, played, won, drawn, lost, goals_for, goals_against, goal_difference, "
        "points, matchweek FROM gold.league_table_current WHERE club_id = %s",
        (club_id,),
    )
    form = _rows(ctx, "SELECT form, points FROM gold.club_form_last5 WHERE club_id = %s",
                 (club_id,))  # fmt: skip
    squad = _rows(ctx, "SELECT count(*) AS n FROM silver.players WHERE club_id = %s", (club_id,))
    return {
        **info,
        "source_id": f"c{club_id}",
        "table": standing[0] if standing else None,
        "form_last5_oldest_first": form[0] if form else None,
        "squad_size": squad[0]["n"],
        "next_fixture": (get_fixtures(ctx, club=info["name"], limit=1)["fixtures"] or [None])[0],
        "last_result": (get_results(ctx, club=info["name"], limit=1)["results"] or [None])[0],
    }


def get_head_to_head(ctx, club_a: str, club_b: str) -> dict:
    a, err_a = _club_id(ctx, club_a)
    b, err_b = _club_id(ctx, club_b)
    if err_a or err_b:
        return err_a or err_b
    rows = _rows(ctx, f"SELECT {MATCH_COLS} FROM gold.head_to_head(%s, %s)", (a, b))
    return {"season": "2026-27", "matches": [_match(r) for r in rows]}


def search_news(ctx, query: str, club: str | None = None, days: int | None = None,
                k: int = 5, include_fantasy: bool = False) -> dict:  # fmt: skip
    club_id, err = _club_id(ctx, club)
    if err:
        return err
    date_from = (ctx.now - timedelta(days=days)).date() if days else None
    hits = retrieval.search(ctx.conn, ctx.provider, query, k=min(k, 10),
                            club_ids=[club_id] if club_id else None, date_from=date_from,
                            exclude_fantasy=not include_fantasy, now=ctx.now)  # fmt: skip
    checked = ctx.shield(hits, query)
    if checked.error:
        return {"error": "news retrieval is unavailable right now (safety check failed); "
                         "say so and do not answer from memory", "results": []}  # fmt: skip
    # the model sees a source_id to cite, not the URL (URLs are built server-side when citing)
    results = [{"source_id": f"a{h['article_id']}", **{k: h[k] for k in ("title", "date", "text")}}
               for h in checked.safe]  # fmt: skip
    ctx.sources.extend({k: h[k] for k in ("article_id", "title", "date", "url")}
                       for h in checked.safe)  # fmt: skip
    out: dict = {"results": results}
    if checked.flagged:
        out["dropped_by_safety_check"] = len(checked.flagged)
    if not results:
        out["note"] = "no matching articles found"
    return out


def get_weekly_digest(ctx, kind: str = "matchweek_recap") -> dict:
    """The newest stored weekly digest (written on Tuesday and Friday from the same data)."""
    if kind not in ("matchweek_recap", "news_highlights"):
        return {"error": "kind must be matchweek_recap or news_highlights"}
    rows = _rows(ctx, "SELECT headline, period_key, created_at, content FROM digests "
                      "WHERE kind = %s ORDER BY created_at DESC LIMIT 1", (kind,))  # fmt: skip
    if not rows:
        return {"error": f"no {kind.replace('_', ' ')} has been written yet"}
    d = rows[0]
    lines = []
    for section in [{"title": "", "bullets": [d["content"]["intro"]]}] + d["content"]["sections"]:
        for b in section["bullets"]:
            if b:  # each line keeps the sources it was validated against, to cite as usual
                lines.append({"section": section["title"], "text": b["text"],
                              "sources": [{"source_id": s} for s in b["sources"]]})  # fmt: skip
    return {"kind": kind, "period": d["period_key"], "headline": d["headline"],
            "written_at": d["created_at"].isoformat(), "lines": lines}  # fmt: skip


def _schema(name: str, description: str, properties: dict, required: tuple = ()) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(required)}}}  # fmt: skip


CLUB = {"type": "string", "description": "club name or nickname, e.g. 'Spurs', 'Man Utd'"}
DATE = {"type": "string", "description": "YYYY-MM-DD"}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 50}

TOOLS: dict[str, tuple[Any, dict]] = {
    "get_league_table": (get_league_table, _schema(
        "get_league_table", "Premier League table, latest or after a given matchweek.",
        {"as_of_matchweek": {"type": "integer"}})),
    "get_fixtures": (get_fixtures, _schema(
        "get_fixtures", "Upcoming matches (not yet played), soonest first. Times in UTC.",
        {"club": CLUB, "date_from": DATE, "date_to": DATE, "limit": LIMIT})),
    "get_results": (get_results, _schema(
        "get_results", "Finished matches with scores, most recent first (oldest_first for the "
        "start of the season).",
        {"club": CLUB, "matchweek": {"type": "integer"}, "limit": LIMIT,
         "oldest_first": {"type": "boolean"}})),
    "get_match_details": (get_match_details, _schema(
        "get_match_details",
        "One match: score, scorers and assists, cards, substitutions. Give match_id, or two "
        "clubs (and a date when they meet twice; without one the latest played meeting).",
        {"match_id": {"type": "integer"}, "club_a": CLUB, "club_b": CLUB, "date": DATE})),
    "get_match_lineup": (get_match_lineup, _schema(
        "get_match_lineup",
        "Line-ups of one match: formation, starting XI (goalkeeper to attack), substitutes, "
        "captain, manager, and per player goals, assists, cards and when they came on or off. "
        "Give match_id, or a club (plus opponent and/or date; a club alone means its latest "
        "played match). Upcoming matches only have line-ups about an hour before kick-off.",
        {"match_id": {"type": "integer"}, "club": CLUB, "opponent": CLUB, "date": DATE})),
    "get_top_scorers": (get_top_scorers, _schema(
        "get_top_scorers", "Season leaderboard for goals, assists or clean sheets.",
        {"stat": {"type": "string", "enum": list(STATS)}, "limit": LIMIT})),
    "get_player_stats": (get_player_stats, _schema(
        "get_player_stats", "A player's season stats and profile. Fuzzy name match.",
        {"name": {"type": "string"}}, ("name",))),
    "compare_players": (compare_players, _schema(
        "compare_players", "Season stats of up to five players side by side.",
        {"names": {"type": "array", "items": {"type": "string"}, "minItems": 2}}, ("names",))),
    "get_club_info": (get_club_info, _schema(
        "get_club_info", "Club profile: stadium, table position, last-5 form, next fixture, "
        "last result.", {"club": CLUB}, ("club",))),
    "get_head_to_head": (get_head_to_head, _schema(
        "get_head_to_head", "This season's meetings between two clubs, played or scheduled.",
        {"club_a": CLUB, "club_b": CLUB}, ("club_a", "club_b"))),
    "get_weekly_digest": (get_weekly_digest, _schema(
        "get_weekly_digest", "The latest weekly digest: the Tuesday matchweek recap or the "
        "Friday news highlights, each line with its sources. Use for 'what happened this week' "
        "or 'sum up the weekend' questions.",
        {"kind": {"type": "string", "enum": ["matchweek_recap", "news_highlights"]}})),
    "search_news": (search_news, _schema(
        "search_news",
        "Search official premierleague.com articles: news, injuries, quotes, previews, match "
        "reports and context. Returns article text with title, date and url to cite.",
        {"query": {"type": "string"}, "club": CLUB,
         "days": {"type": "integer", "description": "only articles from the last N days"},
         "k": {"type": "integer", "minimum": 1, "maximum": 10},
         "include_fantasy": {"type": "boolean", "description": "include FPL articles"}},
        ("query",))),
}  # fmt: skip

TOOL_SPECS = [schema for _, schema in TOOLS.values()]


def run_tool(ctx: ToolContext, name: str, arguments: dict) -> dict:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    return TOOLS[name][0](ctx, **arguments)
