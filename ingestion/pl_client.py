"""Polite client for the Premier League's public JSON APIs (see docs/data_sources.md)."""

import time
from typing import Any

import httpx

CONTENT_API = "https://footballapi.pulselive.com/content/premierleague/text/EN/"
SDP_API = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api"
COMPETITION = 8
HEADERS = {
    "Origin": "https://www.premierleague.com",
    "User-Agent": "premier-league-chatbot/0.1 (+https://github.com/EliDehaene01/premier-league-chatbot)",
    "Accept": "application/json",
}


class PLClient:
    def __init__(self, delay: float = 0.5, max_retries: int = 4, backoff: float = 1.0):
        self.http = httpx.Client(headers=HEADERS, timeout=30)
        self.delay = delay
        self.max_retries = max_retries
        self.backoff = backoff
        self._last_call = 0.0

    def _get(self, url: str, params: dict | None = None) -> Any:
        for attempt in range(self.max_retries + 1):
            wait = self.delay - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            resp = self.http.get(url, params=params)
            self._last_call = time.monotonic()
            retryable = resp.status_code == 429 or resp.status_code >= 500
            if not retryable or attempt == self.max_retries:
                resp.raise_for_status()
                return resp.json()
            time.sleep(self.backoff * 2**attempt)

    def get_standings(self, season: int) -> dict:
        return self._get(f"{SDP_API}/v5/competitions/{COMPETITION}/seasons/{season}/standings")

    def get_matches(self, season: int) -> list[dict]:
        params: dict = {"competition": COMPETITION, "season": season}
        matches: list[dict] = []
        while True:
            page = self._get(f"{SDP_API}/v2/matches", params)
            matches.extend(page.get("data", []))
            cursor = (page.get("pagination") or {}).get("_next")
            if not cursor:
                return matches
            params = {**params, "_next": cursor}

    def get_articles(self, page: int = 0, page_size: int = 20) -> list[dict]:
        params = {
            "page": page,
            "pageSize": page_size,
            "tagNames": "content-type:article",
            "references": f"SDP_FOOTBALL_COMPETITION:{COMPETITION}",
        }
        return self._get(CONTENT_API, params).get("content", [])
