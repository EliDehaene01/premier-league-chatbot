# premier-league-chatbot

A chatbot about the current Premier League season (2026-27). It answers stats questions (table, results, fixtures, players) through tool calls on structured data, and news questions through RAG over articles from the official Premier League site, always citing the article. It runs locally; weekly digests will be published to GitHub Pages.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how it fits together, [docs/data_sources.md](docs/data_sources.md) for the APIs, and [docs/adr/](docs/adr/) for decisions.

## Quickstart

Requires Python 3.12 and Docker.

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD
docker compose up -d          # Postgres 16 + pgvector, schemas bronze/silver/gold
pip install -e ".[dev]"
pytest -m "not live"          # PLC_LIVE_TESTS=1 pytest -m live hits the real APIs
```

## Status

| Phase | What | Status |
|---|---|---|
| 0 | Setup and data source spike | done |
| 1 | Ingestion: bronze / silver / gold | next |
| 2 | RAG + tools + chat loop | |
| 3 | Evals dataset | |
| 4 | API + React UI | |
| 5 | Weekly digests (GitHub Pages) + own MCP server | |
| 6 | AI Ops: tracing, CI eval gate, dashboards, feedback | |
