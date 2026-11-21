# Ingestion schema

All DDL lives in `backend/db.py` and is idempotent. One season (2026 = 2026-27) for now; tables that need it carry a `season` column.

## bronze

### `bronze.api_responses` (append-only)

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | replay order |
| source | text | `sdp` or `content` |
| endpoint | text | path relative to the API base, e.g. `v2/matches`, `v1/matches/2645195/events` |
| params | jsonb | query parameters, including the `_next` cursor |
| payload | jsonb | the response body, unchanged |
| fetched_at | timestamptz | |
| payload_sha256 | text | of the canonical JSON (sorted keys) |

A trigger raises on UPDATE and DELETE. Pages of paginated endpoints are separate rows.

## silver

Upserted by natural key from bronze (`ingestion/silver.py`, dispatch on `endpoint`). Replaying bronze in id order rebuilds silver exactly.

| Table | Key | From | Holds |
|---|---|---|---|
| `clubs` | club_id (SDP team id) | `v1/.../teams` | name, short_name, abbr, stadium, city, capacity |
| `players` | player_id (SDP) | `v1/.../teams/{id}/squad` | name, first/last name, position, club_id, on_loan, nationality, shirt_number, birth_date (NULL when the API says `Unknown`) |
| `matches` | match_id | `v2/matches` | season, matchweek, kickoff_utc (converted from UK local time), home/away club ids, scores, half-time scores, red cards, period, `is_finished` (generated: period = FullTime), result_type, ground, attendance |
| `match_events` | (match_id, seq) | `v1/matches/{id}/events` | club_id, event_type `goal`/`card`/`sub`, detail (Goal, Penalty, Own; Yellow, SecondYellow, StraightRed), player_id (scorer, carded player, player on), secondary_player_id (assist, player off), minute as published, period. Replaced per match on each load; seq follows the event timestamp. |
| `standings_snapshots` | (season, matchweek, club_id) | `v5/.../standings` | position, played, W/D/L, GF, GA, points, the same split for home and away, fetched_at. One snapshot per matchweek: a later fetch with the same `matchweek` overwrites it. |
| `player_season_stats` | (player_id, snapshot_date) | `v1/.../players/stats/leaderboard` | player_name, club_id, position, raw `stats` jsonb (all 80+ fields, merged across sorts), and generated int columns goals, assists, appearances, starts, minutes, clean_sheets, yellow_cards, red_cards (missing = 0) |
| `articles` | content_id | Content API | title, description, summary, published_at, last_modified, canonical_url, author, tags[], refs (the API's `references`), club_ids[] (from SDP_FOOTBALL_TEAM refs), body_html, body_text (script and style removed, then tags; paragraphs kept as lines), is_fantasy (tag `series:fantasy`) |

## gold

Views and SQL functions over silver, for the Phase 2 tools.

| Object | Returns |
|---|---|
| `league_table_current` | the latest standings snapshot with club names and goal difference |
| `latest_player_stats` | player_season_stats of the latest snapshot date, with club name |
| `top_scorers`, `top_assists` | ranked from `latest_player_stats` (rank ties share a number) |
| `club_results` | one row per club per finished match, from that club's side |
| `club_form_last5` | form string (oldest to newest, e.g. `LWWDW`), points, goals for/against over the last five finished matches |
| `match_results` | matches with club names |
| `matchweek_results(mw)` | `match_results` of one matchweek in the current season |
| `head_to_head(club_a, club_b)` | all meetings between two clubs, either way round |
| `table_moves` | position change per club between the latest two snapshots; empty until there are two |
