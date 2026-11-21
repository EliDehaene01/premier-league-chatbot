"""Bronze -> silver. Parsers are pure (payload -> rows); load_from_bronze replays bronze rows."""

import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

LONDON = ZoneInfo("Europe/London")
ARTICLE_URL = "https://www.premierleague.com/en/news/{id}/{slug}"


def _int(v: Any) -> int | None:
    return None if v is None or v == "" else int(v)


def _date(v: Any) -> str | None:
    """ISO date or None; the API uses 'Unknown' for missing dates."""
    return v if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None


# ---------- parsers ----------


def parse_teams(data: list[dict]) -> list[dict]:
    return [
        {
            "club_id": int(t["id"]),
            "name": t["name"],
            "short_name": t.get("shortName"),
            "abbr": t.get("abbr"),
            "stadium": (t.get("stadium") or {}).get("name"),
            "city": (t.get("stadium") or {}).get("city"),
            "capacity": _int((t.get("stadium") or {}).get("capacity")),
        }
        for t in data
    ]


def parse_squad(players: list[dict]) -> list[dict]:
    return [
        {
            "player_id": int(p["id"]["playerId"]),
            "name": p["name"]["display"],
            "first_name": p["name"].get("first"),
            "last_name": p["name"].get("last"),
            "position": p.get("position"),
            "club_id": _int((p.get("currentTeam") or {}).get("id")),
            "on_loan": bool((p.get("currentTeam") or {}).get("loan")),
            "nationality": (p.get("country") or {}).get("country"),
            "shirt_number": _int(p.get("shirtNum")),
            "birth_date": _date((p.get("dates") or {}).get("birth")),
        }
        for p in players
    ]


def kickoff_utc(kickoff: str | None) -> datetime | None:
    """'2026-08-21 20:00:00' is UK local time (kickoffTimezone BST/GMT)."""
    if not kickoff:
        return None
    local = datetime.strptime(kickoff, "%Y-%m-%d %H:%M:%S").replace(tzinfo=LONDON)
    return local.astimezone(UTC)


def parse_matches(data: list[dict]) -> list[dict]:
    rows = []
    for m in data:
        h, a = m["homeTeam"], m["awayTeam"]
        rows.append(
            {
                "match_id": int(m["matchId"]),
                "season": int(m["season"]),
                "matchweek": int(m["matchWeek"]),
                "kickoff_utc": kickoff_utc(m.get("kickoff")),
                "home_club_id": int(h["id"]),
                "away_club_id": int(a["id"]),
                "home_score": h.get("score"),
                "away_score": a.get("score"),
                "home_ht_score": h.get("halfTimeScore"),
                "away_ht_score": a.get("halfTimeScore"),
                "home_red_cards": h.get("redCards"),
                "away_red_cards": a.get("redCards"),
                "period": m.get("period"),
                "result_type": m.get("resultType"),
                "ground": m.get("ground"),
                "attendance": m.get("attendance"),
            }
        )
    return rows


def parse_events(match_id: int, payload: dict) -> list[dict]:
    """goal: player=scorer, secondary=assist. card: player. sub: player=on, secondary=off."""
    events = []
    for side in ("homeTeam", "awayTeam"):
        team = payload.get(side) or {}
        club = int(team["id"])
        for g in team.get("goals") or []:
            pid, assist = g.get("playerId"), g.get("assistPlayerId")
            events.append((club, "goal", g.get("goalType"), pid, assist, g))
        for c in team.get("cards") or []:
            events.append((club, "card", c.get("type"), c.get("playerId"), None, c))
        for s in team.get("subs") or []:
            events.append((club, "sub", None, s.get("playerOnId"), s.get("playerOffId"), s))
    events.sort(key=lambda e: e[5].get("timestamp") or "")
    return [
        {
            "match_id": match_id,
            "seq": seq,
            "club_id": club,
            "event_type": etype,
            "detail": detail,
            "player_id": _int(pid),
            "secondary_player_id": _int(pid2),
            "minute": raw.get("time"),
            "period": raw.get("period"),
        }
        for seq, (club, etype, detail, pid, pid2, raw) in enumerate(events)
    ]


def parse_lineups(match_id: int, payload: dict) -> tuple[list[dict], list[dict]]:
    """(team rows, player rows); both empty while the line-ups are not announced."""
    teams, players = [], []
    for side in ("home_team", "away_team"):
        t = payload.get(side) or {}
        if not t.get("players"):
            continue
        club = int(t["teamId"])
        formation = t.get("formation") or {}
        managers = [m for m in t.get("managers") or [] if m.get("type", "Manager") == "Manager"]
        teams.append({
            "match_id": match_id,
            "club_id": club,
            "formation": formation.get("formation"),
            "manager": " ".join(filter(None, [managers[0].get("firstName"),
                                              managers[0].get("lastName")])) if managers else None,
        })  # fmt: skip
        slot = {pid: (r, o) for r, row in enumerate(formation.get("lineup") or [], 1)
                for o, pid in enumerate(row, 1)}  # fmt: skip
        bench = {pid: o for o, pid in enumerate(formation.get("subs") or [], 1)}
        for p in t["players"]:
            row, order = slot.get(p["id"], (None, bench.get(p["id"])))
            name = p.get("knownName") or " ".join(filter(None, [p.get("firstName"),
                                                                p.get("lastName")]))  # fmt: skip
            players.append({
                "match_id": match_id, "club_id": club, "player_id": int(p["id"]), "name": name,
                "shirt_num": _int(p.get("shirtNum")), "position": p.get("position"),
                "is_captain": bool(p.get("isCaptain")), "is_starter": p["id"] in slot,
                "formation_row": row, "formation_order": order,
            })  # fmt: skip
    return teams, players


def parse_standings(payload: dict, season: int, fetched_at: datetime) -> list[dict]:
    rows = []
    for e in payload["tables"][0]["entries"]:
        o = e["overall"]
        row = {
            "season": season,
            "matchweek": int(payload["matchweek"]),
            "club_id": int(e["team"]["id"]),
            "position": o["position"],
            "played": o["played"],
            "won": o["won"],
            "drawn": o["drawn"],
            "lost": o["lost"],
            "goals_for": o["goalsFor"],
            "goals_against": o["goalsAgainst"],
            "points": o["points"],
            "fetched_at": fetched_at,
        }
        for side in ("home", "away"):
            block = e.get(side) or {}
            for col, key in (
                ("played", "played"),
                ("won", "won"),
                ("drawn", "drawn"),
                ("lost", "lost"),
                ("goals_for", "goalsFor"),
                ("goals_against", "goalsAgainst"),
                ("points", "points"),
            ):
                row[f"{side}_{col}"] = block.get(key)
        rows.append(row)
    return rows


def parse_leaderboard(data: list[dict], snapshot_date: date) -> list[dict]:
    return [
        {
            "player_id": int(d["playerMetadata"]["id"]),
            "snapshot_date": snapshot_date,
            "player_name": d["playerMetadata"].get("name"),
            "club_id": _int((d["playerMetadata"].get("currentTeam") or {}).get("id")),
            "position": d["playerMetadata"].get("position"),
            "stats": d.get("stats") or {},
        }
        for d in data
    ]


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str | None) -> str:
    """Drop script and style elements, then all tags; collapse whitespace, keep paragraphs."""
    if not html:
        return ""
    p = _TextExtractor()
    p.feed(html)
    p.close()
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(p.parts).split("\n"))
    return "\n".join(line for line in lines if line)


def parse_articles(content: list[dict]) -> list[dict]:
    rows = []
    for a in content:
        tags = [t["label"] for t in a.get("tags") or []]
        refs = a.get("references") or []
        modified = a.get("lastModified")
        rows.append(
            {
                "content_id": int(a["id"]),
                "title": a["title"],
                "description": a.get("description"),
                "summary": a.get("summary"),
                "published_at": a.get("date"),
                "last_modified": datetime.fromtimestamp(modified / 1000, UTC) if modified else None,
                # canonicalUrl comes back empty; this URL pattern resolves (checked 2026-11-21)
                "canonical_url": a.get("canonicalUrl")
                or ARTICLE_URL.format(id=a["id"], slug=a.get("titleUrlSegment") or ""),
                "author": a.get("author") or None,
                "tags": tags,
                "refs": Jsonb(refs),
                "club_ids": [int(r["sid"]) for r in refs if r.get("type") == "SDP_FOOTBALL_TEAM"],
                "body_html": a.get("body") or None,
                "body_text": html_to_text(a.get("body")) or None,
                "is_fantasy": "series:fantasy" in tags,
            }
        )
    return rows


# ---------- loading ----------

HAS_UPDATED_AT = {"silver.clubs", "silver.players", "silver.matches", "silver.articles"}


def upsert(conn: psycopg.Connection, table: str, rows: list[dict], key: tuple[str, ...]) -> None:
    if not rows:
        return
    cols = list(rows[0])
    sets = [f"{c} = EXCLUDED.{c}" for c in cols if c not in key]
    if table == "silver.player_season_stats":  # merge stats across leaderboard sorts
        sets = [
            s if not s.startswith("stats ") else "stats = t.stats || EXCLUDED.stats" for s in sets
        ]
    if table in HAS_UPDATED_AT:
        sets.append("updated_at = now()")
    sql = (
        f"INSERT INTO {table} AS t ({', '.join(cols)}) VALUES ({', '.join('%s' for _ in cols)}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {', '.join(sets)}"
    )
    values = [[Jsonb(r[c]) if isinstance(r[c], dict) else r[c] for c in cols] for r in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)


SEASON = r"v1/competitions/8/seasons/(\d+)"


def load_row(conn: psycopg.Connection, endpoint: str, payload: Any, fetched_at: datetime) -> None:
    """Dispatch one bronze row to its silver table. Unknown endpoints are ignored."""
    if endpoint.startswith("content/"):
        upsert(conn, "silver.articles", parse_articles(payload.get("content", [])), ("content_id",))
    elif m := re.fullmatch(r"v5/competitions/8/seasons/(\d+)/standings", endpoint):
        rows = parse_standings(payload, int(m.group(1)), fetched_at)
        upsert(conn, "silver.standings_snapshots", rows, ("season", "matchweek", "club_id"))
    elif endpoint == "v2/matches":
        upsert(conn, "silver.matches", parse_matches(payload.get("data", [])), ("match_id",))
    elif m := re.fullmatch(r"v1/matches/(\d+)/events", endpoint):
        match_id = int(m.group(1))
        conn.execute("DELETE FROM silver.match_events WHERE match_id = %s", (match_id,))
        upsert(conn, "silver.match_events", parse_events(match_id, payload), ("match_id", "seq"))
    elif m := re.fullmatch(r"v3/matches/(\d+)/lineups", endpoint):
        match_id = int(m.group(1))
        teams, players = parse_lineups(match_id, payload)
        if teams:  # an empty (not yet announced) response must not wipe a stored line-up
            conn.execute("DELETE FROM silver.match_lineup_players WHERE match_id = %s", (match_id,))
            upsert(conn, "silver.match_lineups", teams, ("match_id", "club_id"))
            upsert(conn, "silver.match_lineup_players", players, ("match_id", "player_id"))
    elif re.fullmatch(SEASON + r"/teams", endpoint):
        upsert(conn, "silver.clubs", parse_teams(payload.get("data", [])), ("club_id",))
    elif re.fullmatch(SEASON + r"/teams/\d+/squad", endpoint):
        upsert(conn, "silver.players", parse_squad(payload), ("player_id",))
    elif re.fullmatch(SEASON + r"/players/stats/leaderboard", endpoint):
        rows = parse_leaderboard(payload.get("data", []), fetched_at.date())
        upsert(conn, "silver.player_season_stats", rows, ("player_id", "snapshot_date"))


def load_from_bronze(conn: psycopg.Connection, after_id: int = 0) -> int:
    """Replay bronze rows with id > after_id into silver, in fetch order. Returns rows replayed."""
    n = 0
    with conn.transaction(), conn.cursor(name="bronze_replay") as cur:
        cur.itersize = 50
        cur.execute(
            "SELECT endpoint, payload, fetched_at FROM bronze.api_responses "
            "WHERE id > %s ORDER BY id",
            (after_id,),
        )
        for endpoint, payload, fetched_at in cur:
            load_row(conn, endpoint, payload, fetched_at)
            n += 1
    return n
