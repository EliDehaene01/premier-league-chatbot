"""Polite client for the Premier League's public JSON APIs (see docs/data_sources.md)."""

import time
from collections.abc import Callable
from datetime import datetime
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
# Leaderboard sort keys are snake_case; camelCase keys are silently ignored (default order).
LEADERBOARD_SORTS = ("goals", "goal_assists", "clean_sheets", "appearances")

# on_response(source, endpoint, params, payload): called with every successful raw response
ResponseHook = Callable[[str, str, dict, Any], None]


def split_url(url: str) -> tuple[str, str]:
    """('sdp' | 'content', endpoint path relative to that API's base)."""
    if url.startswith(SDP_API):
        return "sdp", url[len(SDP_API) :].lstrip("/")
    return "content", url.replace("https://footballapi.pulselive.com/", "")


class PLClient:
    def __init__(
        self,
        delay: float = 0.5,
        max_retries: int = 4,
        backoff: float = 1.0,
        on_response: ResponseHook | None = None,
    ):
        self.http = httpx.Client(headers=HEADERS, timeout=30)
        self.delay = delay
        self.max_retries = max_retries
        self.backoff = backoff
        self.on_response = on_response
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
                payload = resp.json()
                if self.on_response:
                    self.on_response(*split_url(url), params or {}, payload)
                return payload
            time.sleep(self.backoff * 2**attempt)

    def _paged(self, url: str, params: dict | None = None) -> list[dict]:
        """Follow SDP cursor pagination (pagination._next, passed back as _next)."""
        params = {"_limit": 100, **(params or {})}
        items: list[dict] = []
        while True:
            page = self._get(url, params)
            items.extend(page.get("data", []))
            cursor = (page.get("pagination") or {}).get("_next")
            if not cursor:
                return items
            params = {**params, "_next": cursor}

    def _season(self, season: int) -> str:
        return f"{SDP_API}/v1/competitions/{COMPETITION}/seasons/{season}"

    def get_standings(self, season: int) -> dict:
        return self._get(f"{SDP_API}/v5/competitions/{COMPETITION}/seasons/{season}/standings")

    def get_matches(self, season: int) -> list[dict]:
        return self._paged(f"{SDP_API}/v2/matches", {"competition": COMPETITION, "season": season})

    def get_teams(self, season: int) -> list[dict]:
        return self._paged(f"{self._season(season)}/teams")

    def get_squad(self, season: int, team_id: int | str) -> list[dict]:
        return self._get(f"{self._season(season)}/teams/{team_id}/squad")

    def get_match_events(self, match_id: int | str) -> dict:
        return self._get(f"{SDP_API}/v1/matches/{match_id}/events")

    def get_leaderboard(self, season: int, sort: str = "goals") -> list[dict]:
        url = f"{self._season(season)}/players/stats/leaderboard"
        return self._paged(url, {"_sort": f"{sort}:desc"})

    def get_articles(self, page: int = 0, page_size: int = 20) -> list[dict]:
        params = {
            "page": page,
            "pageSize": page_size,
            "tagNames": "content-type:article",
            "references": f"SDP_FOOTBALL_COMPETITION:{COMPETITION}",
        }
        return self._get(CONTENT_API, params).get("content", [])

    def get_articles_since(self, cutoff: datetime, max_pages: int = 200) -> list[dict]:
        """Page backwards until a page is empty or entirely older than cutoff.

        startDate/endDate filters are ignored by the API, and pageInfo.numEntries is always 0.
        Ordering is newest-first but not strict, hence 'entirely older' rather than 'any older'.
        """
        found: list[dict] = []
        for page in range(max_pages):
            items = self.get_articles(page)
            dated = [(datetime.fromisoformat(a["date"].replace("Z", "+00:00")), a) for a in items]
            found.extend(a for d, a in dated if d >= cutoff)
            if not items or all(d < cutoff for d, _ in dated):
                break
        return found
