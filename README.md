# premier-league-chatbot

A chatbot about the current Premier League season (2026-27). It answers stats questions (table, results, fixtures, players) through tool calls on structured data, and news questions through RAG over articles from the official Premier League site, always citing the article. It runs locally; weekly digests will be published to GitHub Pages.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how it fits together, [docs/data_sources.md](docs/data_sources.md) for the APIs, and [docs/adr/](docs/adr/) for decisions.

## Quickstart

Requires Python 3.12 and Docker.

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD
docker compose up -d          # Postgres 16 + pgvector on host port 5433
pip install -e ".[dev]"
pytest -m "not live"          # unit + db tests; PLC_LIVE_TESTS=1 pytest -m live hits the real APIs
python -m ingestion backfill --season 2026   # first load, about 3 minutes
```

## Ingestion

```bash
python -m ingestion backfill --season 2026   # everything so far this season, articles since 2026-08-01
python -m ingestion matchweek                # latest finished matchweek + articles since last run
python -m ingestion news                     # articles since last run
python -m ingestion rebuild                  # rebuild silver from bronze, no network
```

## Chat

```bash
python -m backend.rag.build_index            # embed new or changed articles (after ingestion)
python -m backend.chat                       # interactive chat; prints tool calls and sources
python -m backend.chat --ask "Who is top of the league?"
python -m evals.retrieval_smoke              # retrieval sanity check: hit@5 and MRR
```

Needs the Azure OpenAI and Content Safety settings in `.env` (see `.env.example`).

Each ingestion mode ends with data-quality checks and exits non-zero if one fails; `--summary out.json` writes a run summary. To schedule the weekly runs on Windows, run `scripts/schedule_windows.ps1` once. Schema: [docs/ingestion_schema.md](docs/ingestion_schema.md).

## Status

| Phase | What | Status |
|---|---|---|
| 0 | Setup and data source spike | done |
| 1 | Ingestion: bronze / silver / gold | done |
| 2 | RAG + tools + chat loop | done |
| 3 | Evals dataset | next |
| 4 | API + React UI | |
| 5 | Weekly digests (GitHub Pages) + own MCP server | |
| 6 | AI Ops: tracing, CI eval gate, dashboards, feedback | |
