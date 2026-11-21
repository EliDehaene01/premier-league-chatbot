"""FastAPI app: uvicorn backend.api.main:create_app --factory --port 8000

POST /api/chat         streams server-sent events (see ARCHITECTURE.md, API)
POST /api/feedback     thumbs up/down on a turn
GET  /api/health       database and data freshness
GET  /api/suggestions  questions built from current data
"""

import json
import queue
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from backend.db import get_connection, init_db
from backend.llm.client import chat
from backend.llm.providers import AzureOpenAIProvider, LLMProvider
from backend.observability import tracing
from backend.tools import ToolContext

MAX_MESSAGE_CHARS = 1000
MAX_MESSAGES = 20  # user + assistant messages per request
RATE_LIMIT = 20  # chat requests per client per minute, per process
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class Message(BaseModel):
    # tool traffic never comes from the client: a client could forge tool results and source ids
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    messages: list[Message] = Field(min_length=1, max_length=MAX_MESSAGES)


class FeedbackRequest(BaseModel):
    turn_id: uuid.UUID
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


WIDGET_TOOLS = {
    "get_league_table": "table",
    "get_fixtures": "matches",
    "get_results": "matches",
    "get_head_to_head": "matches",
    "get_match_lineup": "lineup",
    "get_player_stats": "player",
    "get_top_scorers": "leaders",
}
MATCH_TITLES = {
    "get_fixtures": "Fixtures",
    "get_results": "Results",
    "get_head_to_head": "Head to head",
}


def widgets(tool_results: list[dict]) -> list[dict]:
    """Structured payloads the UI renders as cards, from this turn's successful tool calls."""
    out = []
    for r in tool_results:
        output, kind = r["output"], WIDGET_TOOLS.get(r["name"])
        if not isinstance(output, dict) or "error" in output:
            continue
        if r["name"] == "compare_players":
            out += [
                {"type": "player", "data": p} for p in output.get("players", []) if "error" not in p
            ]
        elif kind == "matches":
            matches = next(
                (output[k] for k in ("fixtures", "results", "matches") if k in output), []
            )
            if matches:
                out.append(
                    {"type": kind, "data": {"title": MATCH_TITLES[r["name"]], "matches": matches}}
                )
        elif kind == "lineup" and not output.get("lineup_announced"):
            continue
        elif kind:
            out.append({"type": kind, "data": output})
    unique = list({json.dumps(w, sort_keys=True, default=str): w for w in out}.values())
    return unique[-4:]


def suggestions(conn: psycopg.Connection) -> list[str]:
    """A few questions built from current data, so the empty state is never stale."""
    out = ["Who is top of the league?"]
    big = conn.execute(
        "SELECT h.short_name, a.short_name FROM silver.matches m "
        "JOIN silver.clubs h ON h.club_id = m.home_club_id "
        "JOIN silver.clubs a ON a.club_id = m.away_club_id "
        "LEFT JOIN gold.league_table_current th ON th.club_id = m.home_club_id "
        "LEFT JOIN gold.league_table_current ta ON ta.club_id = m.away_club_id "
        "WHERE m.period = 'PreMatch' AND m.kickoff_utc > now() "
        "ORDER BY coalesce(th.position, 20) + coalesce(ta.position, 20), m.kickoff_utc LIMIT 1"
    ).fetchone()
    if big:
        out.append(f"When is {big[0]} v {big[1]}, and what's the team news?")
    scorer = conn.execute("SELECT player_name FROM gold.top_scorers LIMIT 1").fetchone()
    if scorer:
        out.append(f"How many goals has {scorer[0]} scored this season?")
    loss = conn.execute(
        "SELECT c.short_name, o.short_name FROM gold.club_results r "
        "JOIN silver.clubs c USING (club_id) JOIN silver.clubs o ON o.club_id = r.opponent_id "
        "JOIN gold.league_table_current t ON t.club_id = r.club_id "
        "WHERE r.goals_for < r.goals_against AND t.position <= 8 "
        "ORDER BY r.kickoff_utc DESC LIMIT 1"
    ).fetchone()
    if loss:
        out.append(f"Why did {loss[0]} lose to {loss[1]}?")
    leader = conn.execute(
        "SELECT c.short_name FROM gold.league_table_current t JOIN silver.clubs c USING (club_id) "
        "WHERE t.position = 1"
    ).fetchone()
    if leader:
        out.append(f"What was {leader[0]}'s starting line-up in their last match?")
    return out


def create_app(
    connect: Callable[[], psycopg.Connection] = get_connection,
    make_provider: Callable[[psycopg.Connection], LLMProvider] | None = None,
    tools: Any = "settings",
) -> FastAPI:
    """tools: the chat's tool backend, an MCP client shared by all requests (see
    mcp_server/client.py); "settings" builds one from TOOL_TRANSPORT, None calls tools directly."""
    if tools == "settings":
        from mcp_server.client import from_settings

        tools = from_settings()
    make_provider = make_provider or (lambda conn: AzureOpenAIProvider(conn, purpose_prefix="api:"))
    app = FastAPI(title="Premier League chatbot")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    hits: dict[str, deque] = defaultdict(deque)
    hits_lock = threading.Lock()

    with connect() as conn:
        init_db(conn)

    def rate_limited(client: str) -> bool:
        # ponytail: in memory, per process; a shared store if this ever runs as several workers
        now = time.monotonic()
        with hits_lock:
            q = hits[client]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= RATE_LIMIT:
                return True
            q.append(now)
            return False

    @app.post("/api/chat")
    def post_chat(req: ChatRequest, request: Request) -> StreamingResponse:
        last = req.messages[-1]
        if last.role != "user" or not last.content.strip():
            raise HTTPException(422, "the last message must be a non-empty user message")
        if len(last.content) > MAX_MESSAGE_CHARS:
            raise HTTPException(422, f"message longer than {MAX_MESSAGE_CHARS} characters")
        if rate_limited(request.client.host if request.client else "unknown"):
            raise HTTPException(429, "too many requests; try again in a minute")
        turn_id = str(uuid.uuid4())
        events: queue.Queue = queue.Queue()

        def worker() -> None:
            started = time.monotonic()
            conn = connect()
            try:
                provider = make_provider(conn)
                ctx = ToolContext(conn, provider, tools=tools)
                turn = chat(
                    [m.model_dump() for m in req.messages],
                    ctx,
                    emit=lambda e, d: events.put((e, d)),
                    session_id=req.conversation_id,
                    tags=["api"],
                )
                latency = int((time.monotonic() - started) * 1000)
                usage = getattr(provider, "usage", None) or {}
                conn.execute(
                    "INSERT INTO chat_turns (turn_id, conversation_id, question, answer, tools, "
                    "sources, prompt_version, cost_usd, latency_ms, trace_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        turn_id,
                        req.conversation_id,
                        last.content,
                        turn.answer,
                        Jsonb(turn.tool_calls),
                        Jsonb(turn.sources),
                        turn.prompt_version,
                        turn.cost_usd,
                        latency,
                        turn.trace_id,
                    ),
                )
                events.put(
                    (
                        "message",
                        {
                            "turn_id": turn_id,
                            "answer": turn.answer,
                            "sources": turn.sources,
                            "widgets": widgets(turn.tool_results),
                            "prompt_version": turn.prompt_version,
                        },
                    )
                )
                tokens = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")}
                events.put(("usage", {**tokens, "cost_usd": turn.cost_usd, "latency_ms": latency}))
            except Exception as e:  # the stream must end with something the UI can show
                events.put(
                    (
                        "error",
                        {
                            "message": "Something went wrong answering that.",
                            "detail": type(e).__name__,
                        },
                    )
                )
            finally:
                conn.close()
                events.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def stream() -> Iterator[str]:
            yield sse("meta", {"turn_id": turn_id, "conversation_id": req.conversation_id})
            while (item := events.get()) is not None:
                yield sse(*item)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/api/feedback")
    def post_feedback(req: FeedbackRequest) -> dict:
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO feedback (turn_id, conversation_id, rating, comment, question, "
                "answer, tools, prompt_version) SELECT turn_id, conversation_id, %s, %s, "
                "question, answer, tools, prompt_version FROM chat_turns WHERE turn_id = %s "
                "RETURNING id, (SELECT trace_id FROM chat_turns WHERE turn_id = %s)",
                (req.rating, req.comment, req.turn_id, req.turn_id),
            ).fetchone()
        if not row:
            raise HTTPException(404, "unknown turn_id")
        # the same rating on the turn's trace, so Langfuse shows it next to the spans
        scored = tracing.score(
            row[1], "user_feedback", 1.0 if req.rating == "up" else 0.0, comment=req.comment
        )
        return {"ok": True, "id": row[0], "traced": scored}

    @app.get("/api/health")
    def health() -> dict:
        try:
            with connect() as conn:
                article, match, matchweek, chunks = conn.execute(
                    "SELECT (SELECT max(published_at) FROM silver.articles), "
                    "(SELECT max(kickoff_utc) FROM silver.matches WHERE is_finished), "
                    "(SELECT max(matchweek) FROM silver.standings_snapshots), "
                    "(SELECT count(*) FROM silver.article_chunks)"
                ).fetchone()
        except psycopg.Error:
            return {"status": "down", "db": False}
        stale = article is None or (datetime.now(UTC) - article).days > 7
        return {
            "status": "degraded" if stale else "ok",
            "db": True,
            "latest_article": article,
            "latest_finished_match": match,
            "table_after_matchweek": matchweek,
            "indexed_chunks": chunks,
        }

    @app.get("/api/digests/latest")
    def latest_digests() -> dict:
        """The newest matchweek recap and news highlights, for the "This week" page."""
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT DISTINCT ON (kind) id, kind, period_key, created_at, headline, content, "
                "sources, facts->'table' AS table FROM digests ORDER BY kind, created_at DESC"
            ).fetchall()
        return {r["kind"]: r for r in rows}

    @app.get("/api/suggestions")
    def get_suggestions() -> dict:
        with connect() as conn:
            return {"suggestions": suggestions(conn)}

    return app
