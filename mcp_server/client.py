"""A synchronous MCP client for the chat loop, which runs in plain threads.

`McpTools` opens one MCP session on a background event loop (an anyio blocking portal) and
exposes two calls the chat loop needs: `specs()` (tool schemas in the chat completions format)
and `call(name, arguments)` (the tool's JSON result). The server can be in-process (the default
in the API: real MCP messages over memory streams, no extra process to run), or a URL of a
server started with `python -m mcp_server --http`.
"""

import json
import threading
from contextlib import ExitStack
from typing import Any

from anyio.from_thread import start_blocking_portal
from mcp import Client


class McpTools:
    def __init__(self, server: Any, timeout: float = 60):
        self._stack = ExitStack()
        self._portal = self._stack.enter_context(start_blocking_portal())
        self._client = self._stack.enter_context(
            self._portal.wrap_async_context_manager(Client(server, read_timeout_seconds=timeout))
        )
        self._lock = threading.Lock()  # one request at a time on the shared session
        self._specs: list[dict] | None = None

    def specs(self) -> list[dict]:
        if self._specs is None:
            with self._lock:
                tools = self._portal.call(self._client.list_tools).tools
            self._specs = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
        return self._specs

    def call(self, name: str, arguments: dict) -> dict:
        with self._lock:
            result = self._portal.call(self._client.call_tool, name, arguments)
        if isinstance(result.structured_content, dict):
            return result.structured_content
        text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        try:
            out = json.loads(text)
        except json.JSONDecodeError:
            out = {"error": text} if result.is_error else {"result": text}
        return out if isinstance(out, dict) else {"result": out}

    def close(self) -> None:
        self._stack.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def from_settings(context=None) -> "McpTools | None":
    """The chat's tool backend per settings: None for direct calls, else an MCP client to the
    server at MCP_URL or, by default, an in-process server built with `context`."""
    from backend.config import settings  # late: keep this module importable without config

    if settings.tool_transport == "direct":
        return None
    if settings.mcp_url:
        return McpTools(settings.mcp_url)
    from mcp_server.server import build_server, default_context

    return McpTools(build_server(context or default_context))
