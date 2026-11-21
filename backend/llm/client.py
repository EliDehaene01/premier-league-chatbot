"""Tool-calling chat loop. Stateless: the caller passes the whole conversation every turn."""

import json
from dataclasses import dataclass, field

from backend.config import settings
from backend.llm.providers import tool_call_message, tool_result_message
from backend.prompts import load_prompt
from backend.tools import TOOL_SPECS, ToolContext, run_tool

MAX_TOOL_ROUNDS = 5


@dataclass
class ChatTurn:
    answer: str
    messages: list[dict]  # the conversation including this turn's tool traffic and answer
    tool_calls: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    cost_usd: float | None = 0.0
    prompt_version: str = ""


def system_prompt(ctx: ToolContext, version: str) -> str:
    completed, upcoming = ctx.conn.execute(
        "SELECT (SELECT max(matchweek) FROM silver.standings_snapshots), "
        "(SELECT min(matchweek) FROM silver.matches WHERE period = 'PreMatch')"
    ).fetchone()
    return load_prompt(
        version,
        today=ctx.now.date().isoformat(),
        completed_matchweek=completed or "unknown",
        next_matchweek=upcoming or "unknown",
    )


def chat(
    messages: list[dict],
    ctx: ToolContext,
    prompt_version: str | None = None,
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> ChatTurn:
    version = prompt_version or settings.prompt_version
    if hasattr(ctx.provider, "prompt_version"):
        ctx.provider.prompt_version = version  # recorded on every llm_calls row
    system = {"role": "system", "content": system_prompt(ctx, version)}
    convo = list(messages)
    turn = ChatTurn(answer="", messages=convo, prompt_version=version)
    sources_before = len(ctx.sources)

    for round_no in range(max_rounds + 1):
        # after max_rounds of tool use, ask for an answer with what it has
        tools = TOOL_SPECS if round_no < max_rounds else None
        result = ctx.provider.chat([system, *convo], tools=tools)
        if turn.cost_usd is not None:
            turn.cost_usd = None if result.cost_usd is None else turn.cost_usd + result.cost_usd
        if not result.tool_calls:
            turn.answer = result.content or ""
            convo.append({"role": "assistant", "content": turn.answer})
            break
        convo.append(tool_call_message(result.content, result.tool_calls))
        for call in result.tool_calls:
            record = {"name": call.name, "arguments": call.arguments}
            try:
                output = run_tool(ctx, call.name, json.loads(call.arguments or "{}"))
            except Exception as e:  # the model sees the error and can recover or explain
                output = {"error": f"{type(e).__name__}: {e}"}
            if isinstance(output, dict) and "error" in output:
                record["error"] = output["error"]
            turn.tool_calls.append(record)
            convo.append(tool_result_message(call.id, output))

    # sources = articles search_news returned that the answer actually links to
    seen = set()
    for s in ctx.sources[sources_before:]:
        if s["article_id"] not in seen and s["url"] in turn.answer:
            seen.add(s["article_id"])
            turn.sources.append(s)
    return turn
