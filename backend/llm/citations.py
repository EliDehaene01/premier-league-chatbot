"""Structured citations.

Tools put a source_id on everything they return: a{content_id} for an article, m{match_id} for
a match, t{matchweek} for the league table, s{date} for the player stats snapshot, c{club_id}
for a club. The model cites with [source_id] markers. Here markers are checked against the ids
that tool results in this conversation actually returned, invalid ones are dropped, valid ones
are renumbered [1], [2], ... and resolved to records whose URLs are built server-side. Links the
model wrote itself, and any "Sources" section it added, are removed.
"""

import re

import psycopg

MATCH_URL = "https://www.premierleague.com/en/match/{id}"
TABLE_URL = "https://www.premierleague.com/en/tables/premier-league"
STATS_URL = "https://www.premierleague.com/en/stats"
CLUB_URL = "https://www.premierleague.com/en/clubs/{id}/{slug}/overview"

SOURCE_ID = r"(?:a\d+|m\d+|t\d+|c\d+|s\d{4}-\d{2}-\d{2})"
ANY_MARKER = re.compile(r"\[\s*([a-z]\d[\w-]*(?:\s*[,;]\s*[a-z]\d[\w-]*)*)\s*\]")
RETURNED_ID = re.compile(rf'"source_id":\s*"({SOURCE_ID})"')
MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BARE_URL = re.compile(r"\s*\(?<?https?://[^\s)>]*[^\s)>.,;:!?]>?\)?")
SOURCES_SECTION = re.compile(r"\n+\s*(?:\*\*|#+\s*)?Sources?\s*:?(?:\*\*)?\s*:?\s*\n.*\Z",
                             re.IGNORECASE | re.DOTALL)  # fmt: skip


def returned_ids(messages: list[dict]) -> set[str]:
    """Source ids that tool results in this conversation returned."""
    ids: set[str] = set()
    for m in messages:
        if m.get("role") == "tool":
            ids.update(RETURNED_ID.findall(m.get("content") or ""))
    return ids


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("&", "and")).strip("-")


def resolve(conn: psycopg.Connection, source_id: str) -> dict | None:
    kind, key = source_id[0], source_id[1:]
    if kind == "a":
        row = conn.execute("SELECT title, published_at::date, canonical_url FROM silver.articles "
                           "WHERE content_id = %s", (int(key),)).fetchone()  # fmt: skip
        return row and {"kind": "article", "title": row[0], "date": str(row[1]), "url": row[2]}
    if kind == "m":
        row = conn.execute(
            "SELECT home_club, away_club, home_score, away_score, period, kickoff_utc::date "
            "FROM gold.match_results WHERE match_id = %s",
            (int(key),),
        ).fetchone()
        if not row:
            return None
        title = (f"{row[0]} {row[2]}-{row[3]} {row[1]}" if row[4] == "FullTime"
                 else f"{row[0]} v {row[1]}")  # fmt: skip
        return {"kind": "match", "title": title, "date": str(row[5]),
                "url": MATCH_URL.format(id=key)}  # fmt: skip
    if kind == "t":
        return {"kind": "table", "title": f"Premier League table after matchweek {key}",
                "date": None, "url": TABLE_URL}  # fmt: skip
    if kind == "s":
        return {"kind": "table", "title": "Premier League player stats", "date": key,
                "url": STATS_URL}  # fmt: skip
    if kind == "c":
        row = conn.execute("SELECT name FROM silver.clubs WHERE club_id = %s",
                           (int(key),)).fetchone()  # fmt: skip
        return row and {"kind": "club", "title": f"{row[0]} club profile", "date": None,
                        "url": CLUB_URL.format(id=key, slug=slug(row[0]))}  # fmt: skip
    return None


def apply(answer: str, messages: list[dict], conn) -> tuple[str, list[dict], list[str]]:
    """Returns (answer with [n] markers, numbered source records, dropped marker ids)."""
    allowed = returned_ids(messages)
    order: list[str] = []
    dropped: list[str] = []
    records: dict[str, dict] = {}

    def number(source_id: str) -> str | None:
        if source_id not in allowed:
            return None
        if source_id not in records:
            record = resolve(conn, source_id)
            if not record:
                return None
            records[source_id] = record
            order.append(source_id)
        return f"[{order.index(source_id) + 1}]"

    def replace(match: re.Match) -> str:
        out = []
        for source_id in re.split(r"\s*[,;]\s*", match.group(1)):
            marker = number(source_id)
            if marker is None:
                dropped.append(source_id)
            elif marker not in out:
                out.append(marker)
        return "".join(out)

    text = SOURCES_SECTION.sub("", answer or "")
    text = MD_LINK.sub(r"\1", text)
    text = BARE_URL.sub("", text)
    text = ANY_MARKER.sub(replace, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text).strip()
    sources = [{"n": i + 1, "id": sid, **records[sid]} for i, sid in enumerate(order)]
    return text, sources, dropped
