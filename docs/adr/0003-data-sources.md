# 0003: Data sources

**Status:** accepted (2026-11-21)

## Context

We need full article text and structured season data. Scraping rendered article pages returned empty bodies in the FPL Manager project and would need a headless browser.

## Decision

Use the JSON APIs that www.premierleague.com calls itself: the Content API for articles (full HTML body included) and the SDP football API for standings, matches, events, teams, squads and player stats. The FPL API is a fallback. All calls go through one polite client. Findings: [data_sources.md](../data_sources.md).

## Consequences

- No Playwright needed; articles come with club and season references for entity linking.
- No published contract: raw responses are kept in bronze and silver runs schema checks.
- Personal, non-commercial, local use; always link back to the article's canonical URL.
