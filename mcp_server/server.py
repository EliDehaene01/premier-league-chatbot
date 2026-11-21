"""Premier League MCP server (MCP Python SDK 2.x `MCPServer`, formerly FastMCP).

Tools are the chat's own tools: their JSON schemas and functions come from backend.tools, so
the chatbot (as an MCP client), Claude Desktop and VS Code all see exactly the same tool layer
and the evals test what users get. Resources and prompts are added with the SDK decorators.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import anyio
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent
from mcp_types import Tool as MCPTool

from backend.db import get_connection
from backend.llm.providers import AzureOpenAIProvider
from backend.observability import tracing
from backend.tools import TOOL_SPECS, ToolContext, get_league_table, get_weekly_digest, run_tool

ContextFactory = Callable[[], AbstractContextManager[ToolContext]]

INSTRUCTIONS = (
    "Premier League 2026-27: table, fixtures, results, line-ups, players, clubs, official news "
    "and the weekly digests. Every result carries source_id values (m = match, a = article, "
    "t = table, s = player stats, c = club); cite them for anything you state."
)


@contextmanager
def default_context() -> Iterator[ToolContext]:
    """A fresh connection per call; embeddings for search_news go through Azure OpenAI."""
    conn = get_connection()
    try:
        yield ToolContext(conn, AzureOpenAIProvider(conn, purpose_prefix="mcp:"))
    finally:
        conn.close()


def _meta(context) -> dict:
    try:
        meta = context.request_context.meta
    except (AttributeError, ValueError):
        return {}
    if meta is None:
        return {}
    return dict(meta) if isinstance(meta, dict) else (getattr(meta, "model_extra", None) or {})


def _level(output) -> dict:
    if isinstance(output, dict) and "error" in output:
        return {"level": "ERROR", "status_message": str(output["error"])[:200]}
    return {}


class PremierLeagueServer(MCPServer):
    def __init__(self, context: ContextFactory = default_context):
        super().__init__("premier-league", instructions=INSTRUCTIONS, version="0.5.0")
        self.context = context
        self._register_resources_and_prompts()

    # ---------- tools: the chat's schemas and functions, served as they are

    async def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(name=f["name"], description=f["description"], input_schema=f["parameters"])
            for f in (spec["function"] for spec in TOOL_SPECS)
        ]

    async def call_tool(self, name, arguments, context=None) -> CallToolResult:
        parent = tracing.parse_traceparent(_meta(context).get("traceparent"))

        def run() -> dict:
            # joins the caller's trace when it sent one; a client like Claude Desktop gets its own
            with tracing.observe(
                f"mcp:{name}", as_type="tool", input=arguments, trace_context=parent
            ) as span:
                with self.context() as ctx:
                    try:
                        output = run_tool(ctx, name, arguments or {})
                    except TypeError as e:  # unexpected or missing arguments
                        output = {"error": f"bad arguments for {name}: {e}"}
                span.update(output=output, **_level(output))
            if parent is None:
                tracing.flush()
            return output

        output = await anyio.to_thread.run_sync(run)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(output, default=str))],
            structured_content=json.loads(json.dumps(output, default=str)),
            is_error="error" in output,
        )

    # ---------- resources and prompts

    def _register_resources_and_prompts(self) -> None:
        def read(fn, **kwargs) -> str:
            with self.context() as ctx:
                return json.dumps(fn(ctx, **kwargs), default=str, indent=1)

        @self.resource(
            "digest://matchweek/latest", name="Latest matchweek recap", mime_type="application/json"
        )
        def latest_recap() -> str:
            return read(get_weekly_digest, kind="matchweek_recap")

        @self.resource(
            "digest://news/latest", name="Latest news highlights", mime_type="application/json"
        )
        def latest_news() -> str:
            return read(get_weekly_digest, kind="news_highlights")

        @self.resource("table://current", name="Current league table", mime_type="application/json")
        def table() -> str:
            return read(get_league_table)

        @self.prompt(description="Preview a club's next match from fixtures, form and news.")
        def matchweek_preview(club: str) -> str:
            return (
                f"Preview {club}'s next Premier League match. Use get_club_info for form "
                f"and the next fixture, get_head_to_head for this season's meetings, and "
                f"search_news for team news. Cite every fact with its source_id."
            )

        @self.prompt(description="Explain how a club's league position changed.")
        def explain_table_move(club: str) -> str:
            return (
                f"Explain how {club}'s league position changed in the latest matchweek. "
                f"Use get_weekly_digest (matchweek_recap) for the moves, get_results for "
                f"their latest result and search_news for context. Cite every fact."
            )


def build_server(context: ContextFactory = default_context) -> PremierLeagueServer:
    return PremierLeagueServer(context)
