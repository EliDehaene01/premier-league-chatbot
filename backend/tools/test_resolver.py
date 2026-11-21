from backend.tools.resolver import resolve_club_in, resolve_player_in

CLUBS = [
    {"id": 3, "name": "Arsenal", "short_name": "Arsenal", "abbr": "ARS"},
    {"id": 6, "name": "Tottenham Hotspur", "short_name": "Spurs", "abbr": "TOT"},
    {"id": 1, "name": "Manchester United", "short_name": "Man Utd", "abbr": "MUN"},
    {"id": 43, "name": "Manchester City", "short_name": "Man City", "abbr": "MCI"},
    {"id": 4, "name": "Newcastle United", "short_name": "Newcastle", "abbr": "NEW"},
    {"id": 36, "name": "Brighton and Hove Albion", "short_name": "Brighton", "abbr": "BHA"},
    {"id": 31, "name": "Crystal Palace", "short_name": "Palace", "abbr": "CRY"},
]


def club(name):
    r = resolve_club_in(CLUBS, name)
    return r.match["id"] if r.match else sorted(c["id"] for c in r.candidates)


def test_club_names_aliases_and_abbreviations():
    assert club("Spurs") == 6 and club("tottenham") == 6 and club("TOT") == 6
    assert club("Man Utd") == 1 and club("man u") == 1 and club("Red Devils") == 1
    assert club("Brighton & Hove Albion") == 36 and club("toon") == 4
    assert club("Palace") == 31 and club("Arsnal") == 3  # typo


def test_club_ambiguous_and_unknown():
    assert club("Manchester") == [1, 43]
    assert club("United") == [1, 4]
    r = resolve_club_in(CLUBS, "Wolves")
    assert r.match is None and "no Premier League" in r.error("club", "Wolves")["error"]


PLAYERS = [
    {"id": 1, "name": "Erling Haaland", "club": "Manchester City"},
    {"id": 2, "name": "Bukayo Saka", "club": "Arsenal"},
    {"id": 3, "name": "Gabriel Magalhães", "club": "Arsenal"},
    {"id": 4, "name": "Gabriel Martinelli", "club": "Arsenal"},
    {"id": 5, "name": "Gabriel Jesus", "club": "Arsenal"},
]


def player(name):
    r = resolve_player_in(PLAYERS, name)
    return r.match["id"] if r.match else sorted(c["id"] for c in r.candidates)


def test_player_full_surname_accents_and_typos():
    assert player("Erling Haaland") == 1 and player("haaland") == 1 and player("Halaand") == 1
    assert player("Magalhaes") == 3 and player("saka") == 2


def test_player_ambiguous_returns_candidates():
    assert player("Gabriel") == [3, 4, 5]
    assert player("Nobody Atall") == []
