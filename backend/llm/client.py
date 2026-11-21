"""Tool-calling chat loop. Stateless: the caller passes the whole conversation every turn."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.config import settings
from backend.llm import citations
from backend.llm.providers import tool_call_message, tool_result_message
from backend.prompts import load_prompt
from backend.tools import TOOL_SPECS, ToolContext, run_tool

MAX_TOOL_ROUNDS = 5

# emit(event, data): "tool_call" {name, arguments, status: started|finished, error?} and
# "token" {text}. The API turns these into server-sent events.
Emit = Callable[[str, dict], None]


@dataclass
class ChatTurn:
    answer: str  # with validated [n] markers, model-written links removed
    messages: list[dict]  # the conversation including this turn's tool traffic and answer
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)  # {name, arguments, output}
    sources: list[dict] = field(default_factory=list)  # {n, id, kind, title, date, url}
    dropped_markers: list[str] = field(default_factory=list)
    raw_answer: str = ""
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
    emit: Emit | None = None,
) -> ChatTurn:
    version = prompt_version or settings.prompt_version
    if hasattr(ctx.provider, "prompt_version"):
        ctx.provider.prompt_version = version  # recorded on every llm_calls row
    system = {"role": "system", "content": system_prompt(ctx, version)}
    convo = list(messages)
    turn = ChatTurn(answer="", messages=convo, prompt_version=version)
    stream = emit is not None and hasattr(ctx.provider, "chat_stream")

    for round_no in range(max_rounds + 1):
        # after max_rounds of tool use, ask for an answer with what it has
        tools = TOOL_SPECS if round_no < max_rounds else None
        if stream:

            def on_delta(text: str) -> None:
                emit("token", {"text": text})

            result = ctx.provider.chat_stream([system, *convo], tools=tools, on_delta=on_delta)
        else:
            result = ctx.provider.chat([system, *convo], tools=tools)
        if turn.cost_usd is not None:
            turn.cost_usd = None if result.cost_usd is None else turn.cost_usd + result.cost_usd
        if not result.tool_calls:
            turn.raw_answer = result.content or ""
            convo.append({"role": "assistant", "content": turn.raw_answer})
            break
        convo.append(tool_call_message(result.content, result.tool_calls))
        for call in result.tool_calls:
            record = {"name": call.name, "arguments": call.arguments}
            if emit:
                emit("tool_call", {"name": call.name, "arguments": call.arguments,
                                   "status": "started"})  # fmt: skip
            try:
                args = json.loads(call.arguments or "{}")
                output = run_tool(ctx, call.name, args)
            except Exception as e:  # the model sees the error and can recover or explain
                args, output = {}, {"error": f"{type(e).__name__}: {e}"}
            if isinstance(output, dict) and "error" in output:
                record["error"] = output["error"]
            turn.tool_calls.append(record)
            turn.tool_results.append({"name": call.name, "arguments": args, "output": output})
            convo.append(tool_result_message(call.id, output))
            if emit:
                emit(
                    "tool_call",
                    {
                        "name": call.name,
                        "status": "finished",
                        **({"error": record["error"]} if "error" in record else {}),
                    },
                )

    turn.answer, turn.sources, turn.dropped_markers = citations.apply(
        turn.raw_answer, convo, ctx.conn
    )
    return turn
