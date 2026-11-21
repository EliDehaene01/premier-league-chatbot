import os
from datetime import UTC, datetime

import httpx
import pytest
import respx

from ingestion.pl_client import CONTENT_API, SDP_API, PLClient


def client() -> PLClient:
    return PLClient(delay=0, backoff=0)


@respx.mock
def test_standings_sends_origin_and_user_agent():
    route = respx.get(f"{SDP_API}/v5/competitions/8/seasons/2026/standings").respond(
        json={"matchweek": 11}
    )
    assert client().get_standings(2026) == {"matchweek": 11}
    req = route.calls.last.request
    assert req.headers["Origin"] == "https://www.premierleague.com"
    assert req.headers["User-Agent"].startswith("premier-league-chatbot/")


@respx.mock
def test_matches_follows_cursor():
    route = respx.get(f"{SDP_API}/v2/matches").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"matchId": 1}], "pagination": {"_next": "abc"}}),
            httpx.Response(200, json={"data": [{"matchId": 2}], "pagination": {"_next": None}}),
        ]
    )
    assert [m["matchId"] for m in client().get_matches(2026)] == [1, 2]
    assert route.calls[1].request.url.params["_next"] == "abc"


@respx.mock
def test_retries_on_429_and_5xx():
    respx.get(f"{SDP_API}/v5/competitions/8/seasons/2026/standings").mock(
        side_effect=[httpx.Response(429), httpx.Response(503), httpx.Response(200, json={})]
    )
    assert client().get_standings(2026) == {}


@respx.mock
def test_gives_up_after_max_retries():
    respx.get(f"{SDP_API}/v5/competitions/8/seasons/2026/standings").respond(500)
    with pytest.raises(httpx.HTTPStatusError):
        PLClient(delay=0, backoff=0, max_retries=1).get_standings(2026)


@respx.mock
def test_no_retry_on_404():
    route = respx.get(f"{SDP_API}/v5/competitions/8/seasons/2026/standings").respond(404)
    with pytest.raises(httpx.HTTPStatusError):
        client().get_standings(2026)
    assert route.call_count == 1


@respx.mock
def test_articles_query_params():
    route = respx.get(CONTENT_API).respond(json={"content": [{"id": 7}]})
    assert client().get_articles(page=2, page_size=5) == [{"id": 7}]
    params = route.calls.last.request.url.params
    assert params["page"] == "2" and params["pageSize"] == "5"
    assert params["references"] == "SDP_FOOTBALL_COMPETITION:8"


@respx.mock
def test_on_response_hook_gets_every_raw_response():
    seen = []
    respx.get(f"{SDP_API}/v1/matches/5/events").respond(json={"homeTeam": {}})
    respx.get(CONTENT_API).respond(json={"content": []})
    c = PLClient(delay=0, on_response=lambda *a: seen.append(a))
    c.get_match_events(5)
    c.get_articles()
    assert seen[0] == ("sdp", "v1/matches/5/events", {}, {"homeTeam": {}})
    assert seen[1][:2] == ("content", "content/premierleague/text/EN/")


@respx.mock
def test_teams_squad_and_leaderboard_paths():
    base = f"{SDP_API}/v1/competitions/8/seasons/2026"
    respx.get(f"{base}/teams").respond(json={"data": [{"id": "3"}], "pagination": {}})
    respx.get(f"{base}/teams/3/squad").respond(json=[{"id": {"playerId": "1"}}])
    board = respx.get(f"{base}/players/stats/leaderboard").respond(
        json={"data": [], "pagination": {"_next": None}}
    )
    c = client()
    assert c.get_teams(2026) == [{"id": "3"}]
    assert c.get_squad(2026, 3) == [{"id": {"playerId": "1"}}]
    c.get_leaderboard(2026, "goal_assists")
    assert board.calls.last.request.url.params["_sort"] == "goal_assists:desc"


def _article(id_, date):
    return {"id": id_, "date": date, "title": "t"}


@respx.mock
def test_articles_since_stops_at_first_page_entirely_older_than_cutoff():
    pages = [
        [_article(1, "2026-11-20T10:00:00Z"), _article(2, "2026-11-01T10:00:00Z")],
        [_article(3, "2026-10-31T10:00:00Z"), _article(4, "2026-11-02T10:00:00Z")],  # unordered
        [_article(5, "2026-10-30T10:00:00Z")],
        [_article(6, "2026-11-05T10:00:00Z")],  # never reached
    ]
    route = respx.get(CONTENT_API).mock(
        side_effect=[httpx.Response(200, json={"content": p}) for p in pages]
    )
    found = client().get_articles_since(datetime(2026, 11, 1, tzinfo=UTC))
    assert [a["id"] for a in found] == [1, 2, 4]
    assert route.call_count == 3


@pytest.mark.live
@pytest.mark.skipif(os.getenv("PLC_LIVE_TESTS") != "1", reason="set PLC_LIVE_TESTS=1")
def test_live_leaderboard_sort_keys_and_squad():
    c = PLClient()
    for sort, stat in (("goal_assists", "goalAssists"), ("clean_sheets", "cleanSheets")):
        top = c._get(
            f"{SDP_API}/v1/competitions/8/seasons/2026/players/stats/leaderboard",
            {"_sort": f"{sort}:desc", "_limit": 5},
        )["data"]
        values = [p["stats"].get(stat, 0) for p in top]
        assert values == sorted(values, reverse=True) and values[0] > 0
    teams = c.get_teams(2026)
    assert len(teams) == 20
    assert c.get_squad(2026, teams[0]["id"])


@pytest.mark.live
@pytest.mark.skipif(os.getenv("PLC_LIVE_TESTS") != "1", reason="set PLC_LIVE_TESTS=1")
def test_live_endpoints():
    c = PLClient()
    standings = c.get_standings(2026)
    assert standings["tables"][0]["entries"]
    articles = c.get_articles(page_size=5)
    assert articles and "title" in articles[0]
    matches = c.get_matches(2026)
    assert len(matches) >= 300
