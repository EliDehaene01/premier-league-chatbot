"""python -m backend.chat: terminal chat. --ask "question" answers one question and exits."""

import argparse
import sys

from backend.db import get_connection, init_db
from backend.llm.client import chat
from backend.llm.providers import AzureOpenAIProvider
from backend.tools import ToolContext


def show(turn) -> None:
    for c in turn.tool_calls:
        err = f"  error: {c['error']}" if "error" in c else ""
        print(f"  [tool] {c['name']}({c['arguments']}){err}")
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
    messages: list[dict] = []
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
        turn = chat(messages, ToolContext(conn, provider))
        messages = turn.messages
        show(turn)
        if args.ask:
            return 0


if __name__ == "__main__":
    sys.exit(main())
