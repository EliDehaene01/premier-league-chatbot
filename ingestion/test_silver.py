from datetime import UTC, date, datetime

from ingestion import sample_payloads as s
from ingestion.silver import (
    html_to_text,
    kickoff_utc,
    parse_articles,
    parse_events,
    parse_leaderboard,
    parse_matches,
    parse_squad,
    parse_standings,
    parse_teams,
)


def test_kickoff_uk_local_time_to_utc():
    assert kickoff_utc("2026-08-21 20:00:00") == datetime(2026, 8, 21, 19, 0, tzinfo=UTC)  # BST
    assert kickoff_utc("2026-11-21 15:00:00") == datetime(2026, 11, 21, 15, 0, tzinfo=UTC)  # GMT
    assert kickoff_utc(None) is None


def test_html_to_text_drops_script_and_style():
    assert html_to_text(s.ARTICLE_BODY) == "Arsenal beat Coventry 3-0.\nNext: away."
    assert html_to_text("") == ""


def test_parse_teams_and_squad():
    clubs = parse_teams(s.TEAMS["data"])
    assert clubs[0] == {
        "club_id": 3, "name": "Arsenal", "short_name": "Arsenal", "abbr": "ARS",
        "stadium": "Emirates Stadium", "city": "London", "capacity": 60704,
    }  # fmt: skip
    (p,) = parse_squad(s.SQUAD)
    assert (p["player_id"], p["club_id"], p["birth_date"], p["on_loan"]) == (109745, 3, None, False)


def test_parse_matches():
    done, todo = parse_matches(s.MATCHES["data"])
    assert (done["match_id"], done["home_score"], done["away_ht_score"]) == (2645195, 3, 0)
    assert todo["home_score"] is None and todo["period"] == "PreMatch"


def test_parse_events_ordered_and_mapped():
    rows = parse_events(2645195, s.EVENTS)
    assert [(r["seq"], r["event_type"], r["minute"]) for r in rows] == [
        (0, "goal", "15"), (1, "card", "27"), (2, "goal", "49"), (3, "sub", "68"),
    ]  # fmt: skip
    assert (rows[0]["player_id"], rows[0]["secondary_player_id"]) == (219847, 466075)
    assert rows[1]["club_id"] == 9 and rows[1]["detail"] == "Yellow"
    assert (rows[3]["player_id"], rows[3]["secondary_player_id"]) == (481655, 204480)


def test_parse_standings_home_away_split():
    rows = parse_standings(s.STANDINGS, 2026, datetime.now(UTC))
    assert rows[0]["points"] == 3 and rows[0]["home_won"] == 1 and rows[1]["away_lost"] == 1


def test_parse_leaderboard_keeps_raw_stats():
    (r,) = parse_leaderboard(s.LEADERBOARD_GOALS["data"], date(2026, 11, 21))
    assert r["player_id"] == 219847 and r["club_id"] == 3 and r["stats"]["goals"] == 1.0


def test_parse_articles():
    news, fpl = parse_articles(s.ARTICLES["content"])
    assert news["canonical_url"] == (
        "https://www.premierleague.com/en/news/4764661/arsenal-3-0-coventry"
    )
    assert news["club_ids"] == [3] and not news["is_fantasy"]
    assert news["body_text"] == "Arsenal beat Coventry 3-0.\nNext: away."
    assert fpl["is_fantasy"] and fpl["body_text"] is None and fpl["author"] is None
