import os

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
