"""python -m mcp_server [--http [--port 8765]]

stdio by default, for Claude Desktop and VS Code, which start the server themselves; --http
serves Streamable HTTP on localhost for clients that connect by URL. Needs the same .env as the
chatbot (database; Azure OpenAI for search_news embeddings; Content Safety for Prompt Shields).
"""

import argparse
import sys

from mcp_server.server import build_server


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mcp_server")
    ap.add_argument("--http", action="store_true", help="Streamable HTTP instead of stdio")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    server = build_server()
    if args.http:
        server.run("streamable-http", host="127.0.0.1", port=args.port)
    else:
        server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
