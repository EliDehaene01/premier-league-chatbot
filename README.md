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

## Web app

Runs on your machine only; nothing is deployed.

```bash
uvicorn backend.api.main:create_app --factory --port 8000   # API (needs the .env settings)
cd frontend && npm ci && npm run dev                          # UI on http://localhost:5173
```

Frontend checks: `npm run lint`, `npm test`, `npm run build`.

## Weekly digests

```bash
python -m digests recap                  # matchweek recap for the latest complete matchweek
python -m digests news                   # news highlights for the past 7 days
python -m digests publish --out preview  # render the GitHub Pages site into a folder
python -m digests publish --push         # commit it to the gh-pages branch and push
python -m evals.digests                  # digest evals on past weeks
```

The scheduled runs (`scripts/schedule_windows.ps1`) write and publish them on Tuesday and Friday mornings. GitHub Pages serves the `gh-pages` branch (Settings > Pages > Deploy from a branch).

## Evals

```bash
pip install -e ".[dev,eval]"
python -m evals.run --dataset chat_v1                 # 165 cases, about $1, rewrites docs/EVAL_RESULTS.md
python -m evals.run --subset smoke                    # 25 cases, about $0.15
python -m evals.run --category news --no-judges       # one category, code checks only
python -m evals.run --compare evals/results/A.json evals/results/B.json
```

Exits non-zero below `evals/thresholds.yaml`. Latest results: [docs/EVAL_RESULTS.md](docs/EVAL_RESULTS.md).

Weekly ingestion (`matchweek`, `news`) now also embeds new articles; `--no-index` skips that.

Each ingestion mode ends with data-quality checks and exits non-zero if one fails; `--summary out.json` writes a run summary. To schedule the weekly runs on Windows, run `scripts/schedule_windows.ps1` once. Schema: [docs/ingestion_schema.md](docs/ingestion_schema.md).

## Status

| Phase | What | Status |
|---|---|---|
| 0 | Setup and data source spike | done |
| 1 | Ingestion: bronze / silver / gold | done |
| 2 | RAG + tools + chat loop | done |
| 3 | Evals dataset | done |
| 4 | API + React UI + structured citations | done |
| 5 | Weekly digests (GitHub Pages) + own MCP server | in progress |
| 6 | AI Ops: tracing, CI eval gate, dashboards, feedback | |
