# CLAUDE.md

Project memory for Claude Code. Keep it short: `README.md` says what this is, `ARCHITECTURE.md` how it fits together. Only what changes how you should work goes here.

## What this is

A local chatbot about the current Premier League season (2026-27, season id 2026). Stats come from tool calls on structured data in Postgres; news comes from RAG over official premierleague.com articles. Azure OpenAI via Microsoft Foundry is the model layer. Weekly digests, a showcase and the AI Ops dashboard are published to GitHub Pages, and an own MCP server exposes the tools.

## Hard constraints - do not violate

- **Never state a score, position, date or stat without a tool call.** RAG is for articles only, never the source of a number.
- **Retrieved article text passes Prompt Shields before it reaches the model.**
- **Every news answer cites title, date and URL** of the article(s) used.
- **No betting advice. Decline off-topic questions.**
- **Ingestion is polite:** one client (`ingestion/pl_client.py`), project User-Agent, delay between calls, backoff on 429/5xx.
- **Bronze is append-only.** Only `backend/db.py` owns the schema DDL. Silver is built only from bronze (`ingestion/silver.py`), never from a live response.
- **Changes to `llm`, `rag`, `prompts`, `evals`, `digests` or `mcp_server` must run the eval suite** (digests: `python -m evals.digests`). Never lower thresholds to get green.
- **Digests are generated from stored data only**, with citations and fixed, config-driven ranking weights.
- **Secrets only in `.env`.** Never in code, compose files or commits.

## Repo layout (target)

```
ingestion/    # pl_client.py, pulls into bronze, bronze -> silver -> gold
backend/      # config.py, db.py (schema DDL), llm/, rag/, tools/, prompts/ (versioned), chat.py, API
evals/        # eval dataset + runner
mcp_server/   # own Premier League MCP server (FastMCP)
digests/      # weekly digest generation
frontend/     # React UI
db/           # init.sql (extension + schemas only)
docs/         # data_sources.md, adr/
```

## Conventions

- Python 3.12, one `pyproject.toml`, ruff line-length 100.
- Tests live beside the code as `test_*.py`. Tests hitting real APIs are marked `live` and skipped unless `PLC_LIVE_TESTS=1`.
- Prompts are versioned files (`backend/prompts/system_vN.md`), not inline strings; a new behaviour gets a new version, and the version is recorded on every `llm_calls` row.
- Tools return dicts and report problems as `{"error": ...}`; they never raise on bad input.
- One ADR per decision in `docs/adr/`.

## Commands

- Database: `docker compose up -d`
- Install: `pip install -e ".[dev]"`
- Lint: `ruff check .`
- Tests: `pytest -m "not live"` (includes `db` tests, which use a throwaway `plc_test` database on the compose Postgres); live: `PLC_LIVE_TESTS=1 pytest -m live`
- Ingestion: `python -m ingestion backfill|matchweek|news|rebuild` (see README)
- RAG index: `python -m backend.rag.build_index` (after ingestion); chat: `python -m backend.chat`
- Retrieval smoke check: `python -m evals.retrieval_smoke`
- Digests: `python -m digests recap|news|publish` (see README); digest evals: `python -m evals.digests`
- MCP server: `python -m mcp_server` (stdio) or `--http`; the chat uses it in-process unless `TOOL_TRANSPORT=direct`
- Tools are defined once in `backend/tools`; the MCP server serves those schemas unchanged. Add a tool there, never only in `mcp_server`.
- AI Ops: Langfuse `docker compose -f docker-compose.langfuse.yml up -d` (secrets via `python scripts/langfuse_env.py`); freshness `python -m backend.observability.freshness`; feedback loop `python -m evals.feedback review|promote|dismiss`. Tracing goes through `backend/observability/tracing.py` only, and must never break an answer. Tests blank the `LANGFUSE_*` settings.
- Evals: `python -m evals.run --dataset chat_v1` (full, about $0.90) or `--subset smoke`; needs `pip install -e .[eval]`. Never lower `evals/thresholds.yaml` to get green. Every eval run costs Azure credit: run one only when asked; the GitHub eval gate starts by hand only.

## Current phase

- [x] 0 Setup and source spike
- [x] 1 Ingestion: bronze / silver / gold
- [x] 2 RAG + tools + chat loop
- [x] 3 Evals dataset (chat_v1, evaluators, runner, thresholds)
- [x] 4 API + React UI + structured citations
- [x] 5 Weekly digests + own MCP server. Mon 23:30 UTC ingest, Tue 05:00 UTC matchweek recap; Thu 23:00 UTC ingest, Fri 05:00 UTC news highlights; summaries published to GitHub Pages
- [x] 6 AI Ops: Langfuse tracing, eval gate (manual, about $0.90 a run), cost and latency dashboard on Pages, feedback loop
- [x] 7 Clean-up: README getting-started guide for non-programmers, decisions table and MCP explainer in ARCHITECTURE.md, secret scan
