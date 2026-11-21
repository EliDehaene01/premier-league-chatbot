"""Small, hand-trimmed API payloads (shapes as seen on 2026-11-21) for tests. No network."""

SEASON = 2026

TEAMS = {
    "pagination": {"_limit": 100, "_prev": None, "_next": None},
    "data": [
        {"name": "Arsenal", "shortName": "Arsenal", "abbr": "ARS", "id": "3",
         "stadium": {"country": "England", "city": "London", "name": "Emirates Stadium",
                     "capacity": 60704}},
        {"name": "Coventry City", "shortName": "Coventry", "abbr": "COV", "id": "9",
         "stadium": {"country": "England", "city": "Coventry", "name": "CBS Arena",
                     "capacity": 32609}},
    ],
}  # fmt: skip

SQUAD = [
    {"currentTeam": {"loan": 0, "name": "Arsenal", "id": "3", "shortName": "Arsenal"},
     "country": {"isoCode": "ES", "country": "Spain", "demonym": "Spanish"},
     "name": {"last": "Arrizabalaga", "display": "Kepa Arrizabalaga", "first": "Kepa"},
     "shirtNum": 13, "dates": {"joinedClub": "2025-07-01", "birth": "Unknown"},
     "id": {"competitionId": "8", "seasonId": "2026", "playerId": "109745"},
     "position": "Goalkeeper"},
]  # fmt: skip


def _team(id_, name, score, ht):
    return {"id": id_, "name": name, "score": score, "halfTimeScore": ht, "redCards": 0}


MATCHES = {
    "pagination": {"_limit": 100, "_prev": None, "_next": None},
    "data": [
        {"matchId": "2645195", "season": "2026", "matchWeek": 1, "period": "FullTime",
         "kickoff": "2026-08-21 20:00:00", "kickoffTimezone": "BST",
         "resultType": "NormalResult", "ground": "Emirates Stadium, London", "attendance": 60098,
         "homeTeam": _team("3", "Arsenal", 3, 2), "awayTeam": _team("9", "Coventry City", 0, 0)},
        {"matchId": "2645302", "season": "2026", "matchWeek": 2, "period": "PreMatch",
         "kickoff": "2026-11-21 15:00:00", "kickoffTimezone": "GMT",
         "ground": "CBS Arena, Coventry",
         "homeTeam": {"id": "9", "name": "Coventry City"},
         "awayTeam": {"id": "3", "name": "Arsenal"}},
    ],
}  # fmt: skip

EVENTS = {
    "homeTeam": {
        "id": "3", "name": "Arsenal",
        "goals": [
            {"goalType": "Goal", "period": "FirstHalf", "assistPlayerId": "466075", "time": "15",
             "playerId": "219847", "timestamp": "20260821T201446+0100"},
            {"goalType": "Penalty", "period": "SecondHalf", "assistPlayerId": None, "time": "49",
             "playerId": "184029", "timestamp": "20260821T210548+0100"},
        ],
        "cards": [], "subs": [
            {"period": "SecondHalf", "playerOnId": "481655", "playerOffId": "204480",
             "time": "68", "timestamp": "20260821T212444+0100"},
        ],
    },
    "awayTeam": {
        "id": "9", "name": "Coventry City", "goals": [], "subs": [],
        "cards": [{"period": "FirstHalf", "time": "27", "type": "Yellow", "playerId": "661888",
                   "timestamp": "20260821T202637+0100"}],
    },
}  # fmt: skip


def _entry(id_, name, pos, w, d, lost, gf, ga):
    block = {"position": pos, "played": w + d + lost, "won": w, "drawn": d, "lost": lost,
             "goalsFor": gf, "goalsAgainst": ga, "points": 3 * w + d}  # fmt: skip
    return {"team": {"id": id_, "name": name}, "overall": block, "home": block, "away": block}


STANDINGS = {
    "matchweek": 1,
    "season": {"id": "2026"},
    "deductions": [],
    "tables": [{"entries": [_entry("3", "Arsenal", 1, 1, 0, 0, 3, 0),
                            _entry("9", "Coventry City", 2, 0, 0, 1, 0, 3)]}],
}  # fmt: skip

LEADERBOARD_GOALS = {
    "pagination": {"_next": None},
    "data": [
        {"playerMetadata": {"id": "219847", "name": "Kai Havertz", "position": "Forward",
                            "currentTeam": {"id": "3", "name": "Arsenal"}},
         "stats": {"goals": 1.0, "appearances": 1.0, "timePlayed": 90.0}},
    ],
}  # fmt: skip

LEADERBOARD_ASSISTS = {
    "pagination": {"_next": None},
    "data": [
        {"playerMetadata": {"id": "219847", "name": "Kai Havertz", "position": "Forward",
                            "currentTeam": {"id": "3", "name": "Arsenal"}},
         "stats": {"goalAssists": 2.0, "appearances": 1.0}},
    ],
}  # fmt: skip

ARTICLE_BODY = (
    '<link rel="stylesheet" href="x.css"><script>window.X = 1;</script>'
    "<style>p {color: red}</style><p>Arsenal beat <b>Coventry</b> 3-0.</p><p>Next: away.</p>"
)

ARTICLES = {
    "pageInfo": {"page": 0, "numPages": 0, "pageSize": 20, "numEntries": 0},
    "content": [
        {"id": 4764661, "title": "Arsenal 3-0 Coventry", "description": "d", "summary": "s",
         "date": "2026-08-22T10:00:00Z", "lastModified": 1787392800000, "canonicalUrl": "",
         "titleUrlSegment": "arsenal-3-0-coventry", "author": "",
         "tags": [{"id": 1, "label": "label:News"}, {"id": 2, "label": "series:news"}],
         "references": [{"id": 3, "type": "SDP_FOOTBALL_TEAM", "sid": "3"},
                        {"id": 2026, "type": "SDP_FOOTBALL_SEASON", "sid": "2026"}],
         "body": ARTICLE_BODY},
        {"id": 2884829, "title": "FPL price changes", "description": "fpl", "summary": "fpl",
         "date": "2026-08-23T01:00:00Z", "lastModified": 1787446800000, "canonicalUrl": "",
         "titleUrlSegment": "fpl-price-changes", "author": "",
         "tags": [{"id": 715, "label": "series:fantasy"}], "references": [], "body": ""},
    ],
}  # fmt: skip
