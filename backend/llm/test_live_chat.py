"""One real question per category against the local database and Azure. Marked live."""

import os

import pytest

from backend.db import get_connection
from backend.llm.client import chat
from backend.llm.providers import AzureOpenAIProvider
from backend.tools import ToolContext

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("PLC_LIVE_TESTS") != "1", reason="set PLC_LIVE_TESTS=1"),
]


@pytest.fixture(scope="module")
def ask():
    conn = get_connection()
    provider = AzureOpenAIProvider(conn)
    return lambda q: chat([{"role": "user", "content": q}], ToolContext(conn, provider))


def test_stats_question_uses_a_tool_and_the_real_leader(ask):
    leader = (
        get_connection()
        .execute("SELECT club FROM gold.league_table_current WHERE position = 1")
        .fetchone()[0]
    )
    turn = ask("Who is top of the Premier League?")
    assert "get_league_table" in [c["name"] for c in turn.tool_calls]
    assert leader.split()[0] in turn.answer


def test_news_question_cites_articles(ask):
    turn = ask("What is the latest injury news at Liverpool?")
    assert "search_news" in [c["name"] for c in turn.tool_calls]
    assert turn.sources and all(s["url"] in turn.answer for s in turn.sources)


def test_off_topic_is_declined_without_tools(ask):
    turn = ask("Give me a pasta recipe")
    assert turn.tool_calls == [] and turn.sources == []
