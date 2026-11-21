"""Single owner of the database schema (see CLAUDE.md). DDL is idempotent; run init_db() freely."""

import psycopg

from backend.config import settings

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- bronze: raw API responses, append-only
CREATE TABLE IF NOT EXISTS bronze.api_responses (
    id             bigserial PRIMARY KEY,
    source         text NOT NULL,              -- 'sdp' | 'content'
    endpoint       text NOT NULL,              -- path relative to the API base
    params         jsonb NOT NULL DEFAULT '{}',
    payload        jsonb NOT NULL,
    fetched_at     timestamptz NOT NULL DEFAULT now(),
    payload_sha256 text NOT NULL
);
CREATE INDEX IF NOT EXISTS api_responses_endpoint_idx ON bronze.api_responses (endpoint);
CREATE OR REPLACE FUNCTION bronze.forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'bronze.api_responses is append-only'; END $$;
DROP TRIGGER IF EXISTS api_responses_append_only ON bronze.api_responses;
CREATE TRIGGER api_responses_append_only BEFORE UPDATE OR DELETE ON bronze.api_responses
    FOR EACH ROW EXECUTE FUNCTION bronze.forbid_change();

-- silver: typed rows, upserted by natural key, rebuilt from bronze
CREATE TABLE IF NOT EXISTS silver.clubs (
    club_id    int PRIMARY KEY,
    name       text NOT NULL,
    short_name text,
    abbr       text,
    stadium    text,
    city       text,
    capacity   int,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS silver.players (
    player_id    int PRIMARY KEY,
    name         text NOT NULL,
    first_name   text,
    last_name    text,
    position     text,
    club_id      int,
    on_loan      boolean,
    nationality  text,
    shirt_number int,
    birth_date   date,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS silver.matches (
    match_id        int PRIMARY KEY,
    season          int NOT NULL,
    matchweek       int NOT NULL,
    kickoff_utc     timestamptz,
    home_club_id    int NOT NULL,
    away_club_id    int NOT NULL,
    home_score      int,
    away_score      int,
    home_ht_score   int,
    away_ht_score   int,
    home_red_cards  int,
    away_red_cards  int,
    period          text,                     -- PreMatch, FirstHalf, ..., FullTime
    is_finished     boolean GENERATED ALWAYS AS (period = 'FullTime') STORED,
    result_type     text,
    ground          text,
    attendance      int,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS matches_matchweek_idx ON silver.matches (season, matchweek);

CREATE TABLE IF NOT EXISTS silver.match_events (
    match_id            int NOT NULL,
    seq                 int NOT NULL,
    club_id             int NOT NULL,
    event_type          text NOT NULL,        -- goal | card | sub
    detail              text,                 -- goalType (Goal, Penalty, OwnGoal) or card type
    player_id           int,                  -- scorer, carded player, or player coming on
    secondary_player_id int,                  -- assist provider, or player going off
    minute              text,                 -- as published, e.g. '45+2'
    period              text,
    PRIMARY KEY (match_id, seq)
);

CREATE TABLE IF NOT EXISTS silver.standings_snapshots (
    season        int NOT NULL,
    matchweek     int NOT NULL,
    club_id       int NOT NULL,
    position      int NOT NULL,
    played        int NOT NULL,
    won           int NOT NULL,
    drawn         int NOT NULL,
    lost          int NOT NULL,
    goals_for     int NOT NULL,
    goals_against int NOT NULL,
    points        int NOT NULL,
    home_played int, home_won int, home_drawn int, home_lost int,
    home_goals_for int, home_goals_against int, home_points int,
    away_played int, away_won int, away_drawn int, away_lost int,
    away_goals_for int, away_goals_against int, away_points int,
    fetched_at    timestamptz NOT NULL,
    PRIMARY KEY (season, matchweek, club_id)
);

-- a leaderboard stat as int; the API omits zero values
CREATE OR REPLACE FUNCTION silver.stat(stats jsonb, key text) RETURNS int
    LANGUAGE sql IMMUTABLE AS $$ SELECT coalesce((stats->>key)::numeric, 0)::int $$;

-- Typed columns derive from the merged stats jsonb: the leaderboard omits zero values and each
-- sort returns a different subset of players, so several sorts are merged per snapshot.
CREATE TABLE IF NOT EXISTS silver.player_season_stats (
    player_id     int NOT NULL,
    snapshot_date date NOT NULL,
    player_name   text,
    club_id       int,
    position      text,
    stats         jsonb NOT NULL,
    goals         int GENERATED ALWAYS AS (silver.stat(stats, 'goals')) STORED,
    assists       int GENERATED ALWAYS AS (silver.stat(stats, 'goalAssists')) STORED,
    appearances   int GENERATED ALWAYS AS (silver.stat(stats, 'appearances')) STORED,
    starts        int GENERATED ALWAYS AS (silver.stat(stats, 'starts')) STORED,
    minutes       int GENERATED ALWAYS AS (silver.stat(stats, 'timePlayed')) STORED,
    clean_sheets  int GENERATED ALWAYS AS (silver.stat(stats, 'cleanSheets')) STORED,
    yellow_cards  int GENERATED ALWAYS AS (silver.stat(stats, 'yellowCards')) STORED,
    red_cards     int GENERATED ALWAYS AS (silver.stat(stats, 'totalRedCards')) STORED,
    PRIMARY KEY (player_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS silver.articles (
    content_id    bigint PRIMARY KEY,
    title         text NOT NULL,
    description   text,
    summary       text,
    published_at  timestamptz,
    last_modified timestamptz,
    canonical_url text NOT NULL,
    author        text,
    tags          text[] NOT NULL DEFAULT '{}',
    refs          jsonb NOT NULL DEFAULT '[]',  -- the API's `references`
    club_ids      int[] NOT NULL DEFAULT '{}',
    body_html     text,
    body_text     text,
    is_fantasy    boolean NOT NULL DEFAULT false,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS articles_published_idx ON silver.articles (published_at DESC);

-- gold: what the chatbot's tools read
CREATE OR REPLACE VIEW gold.league_table_current AS
SELECT s.position, c.name AS club, s.club_id, s.played, s.won, s.drawn, s.lost,
       s.goals_for, s.goals_against, s.goals_for - s.goals_against AS goal_difference,
       s.points, s.matchweek, s.season
FROM silver.standings_snapshots s
JOIN silver.clubs c USING (club_id)
WHERE (s.season, s.matchweek) = (
    SELECT season, max(matchweek) FROM silver.standings_snapshots
    WHERE season = (SELECT max(season) FROM silver.standings_snapshots) GROUP BY season)
ORDER BY s.position;

CREATE OR REPLACE VIEW gold.latest_player_stats AS
SELECT p.*, c.name AS club
FROM silver.player_season_stats p
LEFT JOIN silver.clubs c USING (club_id)
WHERE p.snapshot_date = (SELECT max(snapshot_date) FROM silver.player_season_stats);

CREATE OR REPLACE VIEW gold.top_scorers AS
SELECT rank() OVER (ORDER BY goals DESC) AS rank, player_name, club, goals, assists, appearances,
       minutes, player_id, snapshot_date
FROM gold.latest_player_stats WHERE goals > 0
ORDER BY goals DESC, minutes;

CREATE OR REPLACE VIEW gold.top_assists AS
SELECT rank() OVER (ORDER BY assists DESC) AS rank, player_name, club, assists, goals, appearances,
       minutes, player_id, snapshot_date
FROM gold.latest_player_stats WHERE assists > 0
ORDER BY assists DESC, minutes;

-- one row per club per finished match, from that club's point of view
CREATE OR REPLACE VIEW gold.club_results AS
SELECT m.match_id, m.matchweek, m.kickoff_utc, m.home_club_id AS club_id,
       m.away_club_id AS opponent_id, true AS is_home,
       m.home_score AS goals_for, m.away_score AS goals_against
FROM silver.matches m WHERE m.is_finished
UNION ALL
SELECT m.match_id, m.matchweek, m.kickoff_utc, m.away_club_id, m.home_club_id, false,
       m.away_score, m.home_score
FROM silver.matches m WHERE m.is_finished;

CREATE OR REPLACE VIEW gold.club_form_last5 AS
WITH ranked AS (
    SELECT r.*, row_number() OVER (PARTITION BY club_id ORDER BY kickoff_utc DESC) AS n,
           CASE WHEN goals_for > goals_against THEN 'W'
                WHEN goals_for = goals_against THEN 'D' ELSE 'L' END AS result
    FROM gold.club_results r
)
SELECT c.name AS club, r.club_id,
       string_agg(r.result, '' ORDER BY r.kickoff_utc) AS form,  -- oldest to newest
       sum(CASE r.result WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END)::int AS points,
       sum(r.goals_for)::int AS goals_for, sum(r.goals_against)::int AS goals_against
FROM ranked r JOIN silver.clubs c USING (club_id)
WHERE r.n <= 5
GROUP BY c.name, r.club_id;

CREATE OR REPLACE VIEW gold.match_results AS
SELECT m.match_id, m.season, m.matchweek, m.kickoff_utc, h.name AS home_club, a.name AS away_club,
       m.home_score, m.away_score, m.home_ht_score, m.away_ht_score, m.period, m.ground,
       m.home_club_id, m.away_club_id
FROM silver.matches m
JOIN silver.clubs h ON h.club_id = m.home_club_id
JOIN silver.clubs a ON a.club_id = m.away_club_id;

CREATE OR REPLACE FUNCTION gold.matchweek_results(mw int)
RETURNS SETOF gold.match_results LANGUAGE sql STABLE AS $$
    SELECT * FROM gold.match_results
    WHERE matchweek = mw AND season = (SELECT max(season) FROM silver.matches)
    ORDER BY kickoff_utc, match_id
$$;

CREATE OR REPLACE FUNCTION gold.head_to_head(club_a int, club_b int)
RETURNS SETOF gold.match_results LANGUAGE sql STABLE AS $$
    SELECT * FROM gold.match_results
    WHERE (home_club_id, away_club_id) IN ((club_a, club_b), (club_b, club_a))
    ORDER BY kickoff_utc
$$;

CREATE OR REPLACE VIEW gold.table_moves AS
WITH snaps AS (
    SELECT DISTINCT season, matchweek FROM silver.standings_snapshots
    ORDER BY season DESC, matchweek DESC LIMIT 2
), cur AS (
    SELECT s.* FROM silver.standings_snapshots s
    WHERE (season, matchweek) = (SELECT season, matchweek FROM snaps
                                 ORDER BY season DESC, matchweek DESC LIMIT 1)
), prev AS (
    SELECT s.* FROM silver.standings_snapshots s
    WHERE (season, matchweek) = (SELECT season, matchweek FROM snaps
                                 ORDER BY season, matchweek LIMIT 1)
      AND (SELECT count(*) FROM snaps) = 2
)
SELECT c.name AS club, cur.club_id, prev.matchweek AS from_matchweek,
       cur.matchweek AS to_matchweek, prev.position AS from_position,
       cur.position AS to_position, prev.position - cur.position AS places_gained
FROM cur JOIN prev USING (club_id) JOIN silver.clubs c USING (club_id)
ORDER BY cur.position;
"""


def get_connection(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or settings.dsn, autocommit=True)


def init_db(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(4242)")  # concurrent init_db calls
        conn.execute(DDL)
