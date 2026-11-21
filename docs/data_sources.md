# Data sources

Findings of the Phase 0 spike (run 2026-11-21, season 2026-27, active matchweek 11). Every endpoint below was called for real during the spike; the field lists are what came back.

Both hosts are the same unauthenticated JSON APIs that www.premierleague.com itself calls from the browser. They need an `Origin: https://www.premierleague.com` header and a normal User-Agent. There is no published contract, so the ingestion layer keeps every raw response in bronze and runs schema checks (see [ARCHITECTURE.md](../ARCHITECTURE.md), Ingestion).

## Summary

| Need | Endpoint | Status |
|---|---|---|
| News articles (full text) | Content API `/content/premierleague/text/EN/` | works, full HTML body in the `body` field |
| League table | SDP `v5/competitions/8/seasons/{season}/standings` | works |
| Fixtures and results | SDP `v2/matches?competition=8&season={season}` and `v1/competitions/8/seasons/{season}/matchweeks/{mw}/matches` | works |
| One match | SDP `v1/matches/{matchId}` | works |
| Match events (goals, cards, subs) | SDP `v1/matches/{matchId}/events` | works |
| Clubs (incl. stadium, city, capacity) | SDP `v1/competitions/8/seasons/{season}/teams` | works |
| Squads | SDP `v1/competitions/8/seasons/{season}/teams/{teamId}/squad` | works |
| Player season stats, top scorers | SDP `v1/competitions/8/seasons/{season}/players/stats/leaderboard?_sort=goals:desc` | works (80+ stat fields per player) |
| Fallback players, fixtures, gameweeks | FPL `fantasy.premierleague.com/api/bootstrap-static/` and `/fixtures/` | works (same as the FPL Manager project) |

Ids: competition 8 is the Premier League; season ids are the start year (2026 = 2026-27). www.premierleague.com exposes the active ids in its HTML as `window.ACTIVE_PL_SEASON_ID` and `window.ACTIVE_PL_MATCHWEEK_ID`, and the API base as `window.SDP_API`.

## Content API (articles)

Base: `https://footballapi.pulselive.com/content/premierleague/text/EN/`

Useful query parameters: `pageSize` (20 works); `page` (0-based; about 10 pages cover one month); `tagNames=content-type:article`; `references=SDP_FOOTBALL_COMPETITION:8` to keep Premier League content.

Fields per item: `id`, `title`, `description`, `summary`, `subtitle`, `date`, `lastModified`, `publishFrom` (epoch ms), `tags[].label`, `references[]` (typed links such as `SDP_FOOTBALL_TEAM:3`, `SDP_FOOTBALL_SEASON:2026`), `canonicalUrl`, `author`, `imageUrl`, `body` (HTML).

Findings:

- The full article text is in `body`. It is HTML that starts with a stylesheet link and script elements; removing the script and style elements and then all tags leaves clean text (a 6.4 KB body gave 3.4 KB of text). This solves the empty-body problem the FPL Manager scraper hit on the rendered article pages, and needs no Playwright.
- `references` link each article to clubs and the season by SDP id, which gives entity linking for free.
- Tags carry the article type: `label:Features`, `label:Club News`, `label:Match report`, `series:fantasy`, `franchise:*`, `matchweek:11`, `PLCF News` (community content).
- Some items have an empty `body`: match reports and club-produced (External) articles. For those we keep title, description and summary, and the match data comes from SDP.
- `pageInfo.numEntries` is always 0, so pagination stops when a page comes back empty or older than the cut-off date.
- A large share of items is Fantasy content (`series:fantasy`). The news digest filters it out or weighs it down; the chatbot can still search it.

## SDP football API (structured data)

Base: `https://sdp-prem-prod.premier-league-prod.pulselive.com/api`

- **Standings** (`v5/.../standings`): `matchweek`, `tables[].entries[]` with `team{id,name,shortName,abbr}` and `overall`/`home`/`away` blocks (position, played, won, drawn, lost, goalsFor, goalsAgainst, points, startingPosition).
- **Matches** (`v2/matches`): cursor pagination (`pagination._next`, pass back as `_next`), `matchId`, `matchWeek`, `kickoff` + `kickoffTimezone`, `period` (PreMatch, FullTime, ...), `homeTeam`/`awayTeam` with score, halfTimeScore, redCards, and `ground`.
- **Events** (`v1/matches/{id}/events`): per team goals, cards, subs with period, time, playerId, timestamp.
- **Teams** (`v1/.../teams`): cursor pagination, `stadium{name,city,capacity}`.
- **Squad** (`v1/.../teams/{id}/squad`): name, shirt number, position, country, dates.
- **Leaderboard** (`v1/.../players/stats/leaderboard`): `playerMetadata` (id, name, team, position) and `stats` (goals, shots, minutes, clean sheets, cards and more). `_sort=stat:desc`, `_limit`, cursor pagination.
- Paths that returned 404 or 400 (do not use): `v1/.../standings`, `v2/.../players`, `v2/teams/{id}/squad`, `v2/matches/{id}/events`.

## Etiquette and terms

- robots.txt on www.premierleague.com only blocks tracking query parameters; the API hosts are separate. We stay polite anyway: one client, a project User-Agent, a delay between calls, backoff on 429 and 5xx, and weekly or twice-weekly schedules rather than polling.
- This is a personal, non-commercial portfolio project that runs locally. We store only what the chatbot needs and always link back to the article's `canonicalUrl`.

## Open follow-ups for Phase 1

- Confirm the leaderboard sort keys for assists and clean sheets.
- Check whether `startDate`/`endDate` filters work on the content API (the first test was inconclusive); until then, page backwards until the cut-off date.
- Decide whether the FPL API is still needed once SDP squads and stats are ingested.
