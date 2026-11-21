"""python -m backend.chat: terminal chat. --ask "question" answers one question and exits."""

import argparse
import sys
import uuid

from backend.config import settings
from backend.db import get_connection, init_db
from backend.llm.client import chat
from backend.llm.providers import AzureOpenAIProvider
from backend.observability import tracing
from backend.tools import ToolContext
from mcp_server.client import from_settings


def show(turn) -> None:
    via = "mcp" if settings.tool_transport != "direct" else "direct"
    for c in turn.tool_calls:
        err = f"  error: {c['error']}" if "error" in c else ""
        print(f"  [tool via {via}] {c['name']}({c['arguments']}){err}")
    print(f"\n{turn.answer}\n")
    for s in turn.sources:
        print(f"  [source] {s['title']} ({s['date']}) {s['url']}")
    cost = "unknown" if turn.cost_usd is None else f"${turn.cost_usd:.4f}"
    print(f"  [prompt {turn.prompt_version}, cost {cost}]\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.chat")
    ap.add_argument("--ask", help="ask one question and exit")
    args = ap.parse_args(argv)
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    conn = get_connection()
    init_db(conn)
    provider = AzureOpenAIProvider(conn)
    tools = from_settings()  # the Premier League MCP server, unless TOOL_TRANSPORT=direct
    messages: list[dict] = []
    session = f"cli-{uuid.uuid4()}"
    try:
        return _loop(args, conn, provider, tools, messages, session)
    finally:
        tracing.flush()


def _loop(args, conn, provider, tools, messages, session) -> int:
    while True:
        if args.ask:
            question = args.ask
            print(f"> {question}")
        else:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                return 0
            if question in ("", "exit", "quit"):
                return 0
        messages.append({"role": "user", "content": question})
        turn = chat(
            messages, ToolContext(conn, provider, tools=tools), session_id=session, tags=["cli"]
        )
        messages = turn.messages
        show(turn)
        if args.ask:
            return 0


if __name__ == "__main__":
    sys.exit(main())
