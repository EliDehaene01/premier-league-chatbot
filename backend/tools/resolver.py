"""Club and player name resolution with aliases and fuzzy matching.

Each resolver returns a Resolution: one match, or the candidates when the name is ambiguous or
unknown, so the model can ask the user which one they meant.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

import psycopg

# normalised alias -> club ids (several ids = ambiguous on purpose)
CLUB_ALIASES: dict[str, list[int]] = {
    "gunners": [3], "villa": [7], "villans": [7], "cherries": [91], "bees": [94],
    "seagulls": [36], "brighton": [36], "blues": [8, 11], "chelsea": [8], "sky blues": [9],
    "eagles": [31], "palace": [31], "toffees": [11], "cottagers": [54], "tigers": [88],
    "tractor boys": [40], "whites": [2, 54], "reds": [14, 1], "pool": [14],
    "man city": [43], "manchester city": [43], "city": [43, 88, 9], "citizens": [43],
    "mcfc": [43], "man utd": [1], "man united": [1], "man u": [1], "utd": [1], "mufc": [1],
    "red devils": [1], "united": [1, 2, 4], "magpies": [4], "toon": [4], "nufc": [4],
    "forest": [17], "nottm forest": [17], "notts forest": [17], "black cats": [56],
    "spurs": [6], "tottenham": [6], "thfc": [6], "lfc": [14], "cfc": [8], "afc": [3],
}  # fmt: skip


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


@dataclass
class Resolution:
    match: dict | None = None
    candidates: list[dict] = field(default_factory=list)

    def error(self, kind: str, name: str) -> dict:
        if self.candidates:
            return {"error": f"'{name}' is ambiguous; ask which {kind} the user means, or "
                             "start the answer with 'Assuming you mean <full name>:'",
                    "candidates": self.candidates}  # fmt: skip
        return {"error": f"no Premier League 2026-27 {kind} matches '{name}'"}


def _pick(found: list[dict]) -> Resolution:
    unique = list({c["id"]: c for c in found}.values())
    return Resolution(match=unique[0]) if len(unique) == 1 else Resolution(candidates=unique[:8])


def resolve_club_in(clubs: list[dict], name: str) -> Resolution:
    """clubs: [{id, name, short_name, abbr}]."""
    q = normalize(name)
    by_id = {c["id"]: c for c in clubs}
    keys = {c["id"]: {normalize(c["name"]), normalize(c["short_name"] or ""),
                      normalize(c["abbr"] or "")} for c in clubs}  # fmt: skip
    exact = [by_id[i] for i, k in keys.items() if q in k]
    if exact:
        return _pick(exact)
    if q in CLUB_ALIASES:
        return _pick([by_id[i] for i in CLUB_ALIASES[q] if i in by_id])
    partial = [by_id[i] for i, k in keys.items() if any(q in key.split() or
               (len(q) > 3 and key.startswith(q)) for key in k)]  # fmt: skip
    if partial:
        return _pick(partial)
    names = {normalize(c["name"]): c for c in clubs}
    close = difflib.get_close_matches(q, list(names) + list(CLUB_ALIASES), n=3, cutoff=0.75)
    found = []
    for m in close:
        found += [names[m]] if m in names else [by_id[i] for i in CLUB_ALIASES[m] if i in by_id]
    return _pick(found)


def resolve_player_in(players: list[dict], name: str) -> Resolution:
    """players: [{id, name, club}]. Full name, then surname or first name, then fuzzy."""
    q = normalize(name)
    norm = [(normalize(p["name"]), p) for p in players]
    for test in (
        lambda n: n == q,
        lambda n: q in n.split() or n.endswith(" " + q),
        lambda n: len(q) > 3 and q in n,
    ):
        found = [p for n, p in norm if test(n)]
        if found:
            return _pick(found)
    close = difflib.get_close_matches(q, [n for n, _ in norm], n=5, cutoff=0.8)
    if not close:  # a misspelt surname: match against last names
        last = {n.split()[-1]: n for n, _ in norm}
        close = [last[m] for m in difflib.get_close_matches(q, list(last), n=5, cutoff=0.8)]
    return _pick([p for n, p in norm if n in close])


def load_clubs(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute("SELECT club_id, name, short_name, abbr FROM silver.clubs").fetchall()
    return [{"id": r[0], "name": r[1], "short_name": r[2], "abbr": r[3]} for r in rows]


def load_players(conn: psycopg.Connection) -> list[dict]:
    """Squad players, plus anyone in the stats feed who is not in a current squad."""
    rows = conn.execute(
        "SELECT p.player_id, p.name, c.name FROM silver.players p "
        "LEFT JOIN silver.clubs c USING (club_id) "
        "UNION "
        "SELECT s.player_id, s.player_name, s.club FROM gold.latest_player_stats s "
        "WHERE s.player_id NOT IN (SELECT player_id FROM silver.players)"
    ).fetchall()
    return [{"id": r[0], "name": r[1], "club": r[2]} for r in rows]


def resolve_club(conn, name: str) -> Resolution:
    return resolve_club_in(load_clubs(conn), name)


def resolve_player(conn, name: str) -> Resolution:
    return resolve_player_in(load_players(conn), name)
