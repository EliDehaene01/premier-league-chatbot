import os

# tests never send traces, even when .env holds Langfuse keys (env vars beat .env)
for _key in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    os.environ[_key] = ""

import psycopg  # noqa: E402
import pytest  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.db import init_db  # noqa: E402

TEST_DB = "plc_test"


@pytest.fixture(scope="session")
def db_url():
    """A fresh `plc_test` database on the compose Postgres. Skipped when unreachable (not in CI)."""
    try:
        admin = psycopg.connect(settings.dsn, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as e:
        if os.getenv("CI"):
            raise
        pytest.skip(f"compose Postgres unreachable: {e}")
    with admin:
        admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {TEST_DB}")
    return make_conninfo(settings.dsn, dbname=TEST_DB)


@pytest.fixture
def db(db_url):
    with psycopg.connect(db_url, autocommit=True) as conn:
        init_db(conn)
        conn.execute(
            "TRUNCATE bronze.api_responses, silver.clubs, silver.players, silver.matches, "
            "silver.match_events, silver.standings_snapshots, silver.player_season_stats, "
            "silver.match_lineups, silver.match_lineup_players, silver.articles, "
            "silver.article_chunks, llm_calls, feedback, chat_turns, digests RESTART IDENTITY"
        )
        yield conn
