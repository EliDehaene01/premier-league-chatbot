from datetime import date

from backend.llm.providers import ChatResult
from evals.evaluators import (
    citation,
    exact_answer,
    no_ungrounded_numbers,
    retrieval,
    tool_selection,
    transcript,
    value_found,
)
from evals.evaluators.judges import guardrail


def t(answer="", calls=(), outputs=(), retrieved=(), question="q"):
    return {"question": question, "answer": answer,
            "calls": [{"name": n, "arguments": a} for n, a in calls],
            "tool_outputs": list(outputs), "retrieved": list(retrieved)}  # fmt: skip


def test_value_found_normalises_numbers_names_dates_and_alternatives():
    assert value_found("Arsenal have 27 pts", 27) and not value_found("Arsenal have 127 pts", 27)
    assert value_found("capacity 60,704", 60704)
    assert value_found("Brighton & Hove Albion are 2nd", "Brighton and Hove Albion")
    assert value_found("Man Utd lost", ["Manchester United", "Man Utd"])
    assert value_found("Pascal Groß ran far", "Gro|Gross") and value_found("Gross ran", "Groß")
    assert value_found("on Saturday 21st November", date(2026, 11, 21))
    assert value_found("Nov 21 at 15:00", date(2026, 11, 21))
    assert value_found("2026-11-21", date(2026, 11, 21))
    assert not value_found("on 22 November", date(2026, 11, 21))
    assert value_found("they played 4-2-3-1", "4-2-3-1") and not value_found("4-4-2", "4-2-3-1")


def test_exact_answer_modes():
    rows = [(["Arsenal", "Arsenal"], 27), (["Chelsea", "Chelsea"], 16)]
    assert exact_answer({"golden": {"match": "all"}}, t("Arsenal 27, Chelsea 16"), rows).passed
    partial = exact_answer({"golden": {"match": "all"}}, t("Arsenal 27"), rows)
    assert not partial.passed and partial.score == 0.5 and "Chelsea" in partial.detail
    assert exact_answer({"golden": {"match": "any"}}, t("Arsenal 27"), rows).passed
    assert exact_answer({"golden": {"match": "fraction:0.5"}}, t("Arsenal 27"), rows).passed
    facts = {"golden": {"facts": ["Barnes", "36.21"]}}
    assert exact_answer(facts, t("Harvey Barnes hit 36.21 km/h"), None).passed
    assert not exact_answer(facts, t("Harvey Barnes is quick"), None).passed


def test_tool_selection_recall_precision_and_args():
    case = {"expected_tools": [["get_results", "get_match_details"], "search_news"]}
    assert tool_selection(case, t(calls=[("get_results", {}), ("search_news", {})])).passed
    missing = tool_selection(case, t(calls=[("get_results", {})]))
    assert not missing.passed and "search_news" in missing.detail
    wild = {"expected_tools": ["get_league_table"]}
    calls = [("get_league_table", {}), ("get_fixtures", {}), ("get_results", {})]
    assert not tool_selection(wild, t(calls=calls)).passed  # 1 of 3 calls expected
    none = {"expected_tools": []}
    assert tool_selection(none, t()).passed
    assert not tool_selection(none, t(calls=[("search_news", {})])).passed
    args = {"expected_tools": ["get_results"], "arg_checks": [{"arg": "matchweek", "equals": 9}]}
    assert tool_selection(args, t(calls=[("get_results", {"matchweek": 9})])).passed
    assert not tool_selection(args, t(calls=[("get_results", {"matchweek": 8})])).passed


def test_no_ungrounded_numbers():
    out = ['{"position": 1, "points": 27, "kickoff_utc": "2026-11-21T17:30:00+00:00"}']
    ok = t("1. Arsenal are 1st with 27 points; next game 21 November at 17:30 in 2026-27.",
           outputs=out)  # fmt: skip
    assert no_ungrounded_numbers({}, ok).passed
    bad = no_ungrounded_numbers({}, t("Arsenal have 28 points", outputs=out))
    assert not bad.passed and "28" in bad.detail
    assert no_ungrounded_numbers({}, t("No numbers here")).passed is None
    assert no_ungrounded_numbers({}, t("Matchweek 11 is next"), {"11"}).passed


def test_citation_precision_and_expected_article():
    hit = {"url": "https://www.premierleague.com/en/news/4737123/fastest", "text": "..."}
    case = {"golden": {"articles": [4737123]}}
    good = t(f"Barnes. Source: Fastest players, 2026-11-09, {hit['url']}.", retrieved=[hit])
    assert citation(case, good).passed
    made_up = t("See https://www.premierleague.com/en/news/1/x", retrieved=[hit])
    assert not citation(case, made_up).passed
    assert not citation(case, t("no link", retrieved=[hit])).passed


def test_retrieval_rank():
    case = {"golden": {"articles": [7]}}
    assert retrieval(case, [3, 7, 9]).score == 0.5 and retrieval(case, [3, 7]).passed
    assert not retrieval(case, [1, 2, 3, 4, 5]).passed
    assert retrieval({}, [1]).passed is None


def test_transcript_from_chat_messages():
    messages = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "a", "type": "function",
             "function": {"name": "search_news", "arguments": '{"query": "x"}'}}]},
        {"role": "tool", "tool_call_id": "a",
         "content": '{"results": [{"article_id": 1, "url": "u", "text": "t"}]}'},
        {"role": "assistant", "content": "answer"},
    ]  # fmt: skip
    tr = transcript("x", "answer", messages)
    assert tr["calls"] == [{"name": "search_news", "arguments": {"query": "x"}}]
    assert tr["retrieved"][0]["article_id"] == 1 and len(tr["tool_outputs"]) == 1


class FakeJudge:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def chat(self, messages, tools=None, purpose="chat"):
        self.prompts.append(messages[0]["content"])
        return ChatResult(self.reply)


def test_guardrail_judge_parses_verdict_and_fails_without_one():
    case = {"rubric": "Pass if it declines."}
    judge = FakeJudge('Sure: {"pass": true, "reason": "declined"}')
    assert guardrail(judge, case, t("I can't help with bets")).passed
    assert "Pass if it declines." in judge.prompts[0]
    assert not guardrail(FakeJudge("no json"), case, t("x")).passed
    assert guardrail(FakeJudge(""), {}, t("x")).passed is None
