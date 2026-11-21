import json
from datetime import UTC, datetime

from backend.llm.client import MAX_TOOL_ROUNDS, chat
from backend.llm.fake_provider import FakeProvider, call
from backend.llm.providers import ChatResult
from backend.tools import ToolContext


class FakeConn:
    """Answers the system prompt's matchweek query; tools are monkeypatched in these tests."""

    def execute(self, sql, params=None):
        class R:
            def fetchone(self):
                return (10, 11)

        return R()


def ctx(script):
    return ToolContext(FakeConn(), FakeProvider(script), now=datetime(2026, 11, 21, tzinfo=UTC))


def test_tool_call_then_answer(monkeypatch):
    seen = []

    def fake_tool(c, name, args):
        seen.append((name, args))
        return {"table": ["Arsenal"]}

    monkeypatch.setattr("backend.llm.client.run_tool", fake_tool)
    c = ctx([ChatResult(None, [call("get_league_table", '{"as_of_matchweek": 10}')], 0.001),
             ChatResult("Arsenal are top.", [], 0.002)])  # fmt: skip
    turn = chat([{"role": "user", "content": "Who is top?"}], c)

    assert turn.answer == "Arsenal are top."
    assert seen == [("get_league_table", {"as_of_matchweek": 10})]
    assert turn.tool_calls == [{"name": "get_league_table", "arguments": '{"as_of_matchweek": 10}'}]
    assert abs(turn.cost_usd - 0.003) < 1e-9 and turn.prompt_version == "v1"
    roles = [m["role"] for m in turn.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    # stateless: the second call got the system prompt plus the whole conversation so far
    second = c.provider.chat_calls[1]["messages"]
    assert second[0]["role"] == "system" and "2026-11-21" in second[0]["content"]
    assert "completed matchweek in the data is 10" in second[0]["content"]
    assert json.loads(second[-1]["content"]) == {"table": ["Arsenal"]}


def test_tool_exception_goes_back_to_the_model(monkeypatch):
    def boom(c, name, args):
        raise ValueError("db down")

    monkeypatch.setattr("backend.llm.client.run_tool", boom)
    c = ctx([ChatResult(None, [call("get_results")]), ChatResult("Sorry, no data.", [])])
    turn = chat([{"role": "user", "content": "results?"}], c)
    assert turn.answer == "Sorry, no data."
    assert turn.tool_calls[0]["error"] == "ValueError: db down"
    assert "db down" in c.provider.chat_calls[1]["messages"][-1]["content"]


def test_round_cap_forces_an_answer(monkeypatch):
    monkeypatch.setattr("backend.llm.client.run_tool", lambda c, n, a: {"ok": True})
    script = [ChatResult(None, [call("get_results", id_=f"c{i}")]) for i in range(MAX_TOOL_ROUNDS)]
    c = ctx([*script, ChatResult("Best I can do.", [])])
    turn = chat([{"role": "user", "content": "loop"}], c)
    assert turn.answer == "Best I can do."
    assert len(turn.tool_calls) == MAX_TOOL_ROUNDS
    assert [x["tools"] is None for x in c.provider.chat_calls] == [False] * MAX_TOOL_ROUNDS + [True]


def test_unknown_cost_stays_unknown():
    c = ctx([ChatResult("hi", [], None)])
    assert chat([{"role": "user", "content": "hi"}], c).cost_usd is None


def test_sources_are_only_the_cited_articles(monkeypatch):
    def fake_tool(c, name, args):
        c.sources += [
            {"article_id": 1, "title": "A", "date": "2026-11-20", "url": "u/1"},
            {"article_id": 2, "title": "B", "date": "2026-11-19", "url": "u/2"},
        ]
        return {"results": []}

    monkeypatch.setattr("backend.llm.client.run_tool", fake_tool)
    c = ctx([ChatResult(None, [call("search_news", '{"query": "x"}')]),
             ChatResult("See A (2026-11-20) u/1", [])])  # fmt: skip
    assert [s["article_id"] for s in chat([{"role": "user", "content": "x"}], c).sources] == [1]
