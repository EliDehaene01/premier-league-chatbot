# Architecture

## System overview

A local system: Postgres 16 with pgvector holds all data, a Python backend runs ingestion, retrieval and the chat loop against Azure OpenAI (Microsoft Foundry), and a React UI talks to the backend. Scope is the current season only (2026-27, season id 2026).

## Data sources

The unauthenticated JSON APIs that www.premierleague.com calls itself: the Content API for articles and the SDP football API for structured data, with the FPL API as fallback. Details and field lists: [docs/data_sources.md](docs/data_sources.md), decision: [ADR 0003](docs/adr/0003-data-sources.md).

## Ingestion (bronze/silver/gold)

All HTTP goes through one polite client (`ingestion/pl_client.py`: project User-Agent, 0.5 s delay, backoff on 429/5xx).

- **bronze**: raw API responses, append-only, with fetch time and source URL. Because the APIs have no published contract, every response is kept as-is.
- **silver**: typed, deduplicated rows (matches, standings, teams, players, articles with clean text), with schema checks that fail loudly when the API shape changes.
- **gold**: what the chatbot reads: query-ready tables for tools and chunked, embedded articles for RAG.

Only `backend/db.py` owns table DDL; `db/init.sql` just creates the `vector` extension and the three schemas. *Table design: Phase 1.*

## Why tool calling for stats and RAG for news

Numbers must be exact and current, so they come from SQL-backed tools; articles are prose, so they are retrieved. The model never states a number it did not get from a tool. See [ADR 0001](docs/adr/0001-tool-calling-for-stats-rag-for-news.md).

## RAG pipeline

Articles are cleaned (script/style removed, tags stripped), chunked, embedded and stored in pgvector, filtered by date and club references. Retrieved text passes Prompt Shields before reaching the model; answers cite title, date and URL. *Chunking, embedding model and ranking: Phase 2.*

## Chat loop

*Phase 2.* Decline betting advice and off-topic questions.

## Weekly digests

Generated from stored data only, with citations and fixed config-driven ranking weights, published to GitHub Pages:

- Monday 23:30 UTC ingest, Tuesday 05:00 UTC matchweek recap.
- Thursday 23:00 UTC ingest, Friday 05:00 UTC news highlights.

*Details: Phase 5.*

## MCP server

An own Premier League MCP server (FastMCP) exposing the same tools. See [ADR 0004](docs/adr/0004-own-mcp-server.md). *Phase 5.*

## Evaluation

An eval dataset and runner; changes to llm, rag, prompts, evals or mcp_server must pass it, and thresholds are never lowered to get green. *Phase 3.*

## AI Ops

Self-hosted Langfuse tracing ([ADR 0005](docs/adr/0005-langfuse-for-tracing.md)), a CI eval gate, a cost and latency dashboard and a feedback loop. *Phase 6.*

## Frontend

React UI over the backend API. *Phase 4.*

## Trade-offs

- One Postgres for relational data and vectors instead of a separate vector DB ([ADR 0002](docs/adr/0002-single-postgres-store.md)).
- Undocumented APIs: cheap and complete, but may change without notice; mitigated by keeping raw bronze and schema checks.
- Current season only keeps data small and answers unambiguous.
