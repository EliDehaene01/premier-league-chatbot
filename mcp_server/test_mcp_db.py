"""The MCP server over real MCP sessions (in-process and stdio) on the db test database."""

import json
import os
import sys
from contextlib import contextmanager
from functools import partial

import anyio
import psycopg
import pytest
from mcp import Client, StdioServerParameters

from backend.llm.fake_provider import FakeProvider
from backend.tools import TOOL_SPECS, ToolContext, run_tool
from ingestion.silver import load_from_bronze
from ingestion.test_ingestion_db import fill_bronze
from mcp_server.client import McpTools
from mcp_server.server import build_server

pytestmark = pytest.mark.db


@pytest.fixture
def server(db, db_url):
    fill_bronze(db)
    load_from_bronze(db)
    connect = partial(psycopg.connect, db_url, autocommit=True)

    @contextmanager
    def context():
        with connect() as conn:
            yield ToolContext(conn, FakeProvider())

    return build_server(context)


def test_tools_are_the_chat_tools_with_the_same_results(server, db):
    with McpTools(server) as tools:
        assert tools.specs() == TOOL_SPECS  # one tool layer, no drift between chat and MCP
        direct = run_tool(ToolContext(db, FakeProvider()), "get_league_table", {})
        assert tools.call("get_league_table", {}) == json.loads(json.dumps(direct, default=str))
        assert "error" in tools.call("get_results", {"club": "Wolves"})
        assert "bad arguments" in tools.call("get_results", {"nope": 1})["error"]
        assert "error" in tools.call("no_such_tool", {})


def test_resources_prompts_and_error_flag(server, db):
    db.execute(
        "INSERT INTO digests (kind, period_key, headline, content, facts) VALUES "
        "('matchweek_recap', 'mw1', 'Arsenal start strong', %s, '{}')",
        (
            json.dumps(
                {"intro": {"text": "Arsenal won 3-0.", "sources": ["m2645195"]}, "sections": []}
            ),
        ),
    )

    async def go():
        async with Client(server) as c:
            uris = {str(r.uri) for r in (await c.list_resources()).resources}
            recap = json.loads(
                (await c.read_resource("digest://matchweek/latest")).contents[0].text
            )
            table = json.loads((await c.read_resource("table://current")).contents[0].text)
            prompts = {p.name for p in (await c.list_prompts()).prompts}
            preview = await c.get_prompt("matchweek_preview", {"club": "Arsenal"})
            bad = await c.call_tool("get_results", {"club": "Wolves"})
            return uris, recap, table, prompts, preview, bad

    uris, recap, table, prompts, preview, bad = anyio.run(go)
    assert uris == {"digest://matchweek/latest", "digest://news/latest", "table://current"}
    assert recap["headline"] == "Arsenal start strong"
    assert recap["lines"][0]["sources"] == [{"source_id": "m2645195"}]
    assert table["table"][0]["club"] == "Arsenal"
    assert prompts == {"matchweek_preview", "explain_table_move"}
    assert "Arsenal" in preview.messages[0].content.text
    assert bad.is_error


def test_stdio_server_starts_like_claude_desktop_runs_it(server, db_url):
    """`python -m mcp_server` over stdio, as an MCP host launches it."""
    env = {
        **os.environ,
        "DATABASE_URL": db_url,
        "AZURE_OPENAI_ENDPOINT": "https://example.invalid",
        "AZURE_OPENAI_API_KEY": "test-only",
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server"], env=env)

    async def go():
        async with Client(params, read_timeout_seconds=30) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            result = await c.call_tool("get_league_table", {})
            return names, result.structured_content

    names, table = anyio.run(go)
    assert "get_weekly_digest" in names and table["table"][0]["club"] == "Arsenal"
