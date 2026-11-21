# 0011: AI Ops: traces locally, totals publicly, evals as the gate

**Status:** accepted (2026-11-21)

## Context

Phase 6 adds the operating side: seeing what a single answer did, knowing what the system costs and how fast it is, noticing stale data, learning from bad answers and stopping regressions before they merge. Everything runs on one laptop, the repo is public, and costs should stay near zero.

## Decision

- **Tracing:** self-hosted Langfuse v4 ([ADR 0005](0005-langfuse-for-tracing.md)) from `docker-compose.langfuse.yml`, provisioned headlessly from `.env` (`scripts/langfuse_env.py` writes random secrets). One trace per chat turn, digest run or eval case. The MCP boundary carries the trace as a W3C `traceparent` in the request `_meta`, so the server's spans join the caller's trace; a client like Claude Desktop gets traces of its own. Only our own spans are exported (the MCP SDK's built-in OpenTelemetry spans would duplicate each tool call). Tracing is off without keys and every SDK call is guarded: it can never break an answer.
- **Dashboard:** a static `ops.html` on the GitHub Pages site, rendered with the digests from `llm_calls`, `chat_turns`, `feedback`, `eval_runs` and `freshness_checks`. Totals only, never questions, answers or ids. Not a Langfuse export: Langfuse stays local, and the page needs no running service.
- **Freshness:** six checks (ingestion, results, table, news, index, digests) in `/api/health` and the UI badge, stored after each scheduled ingestion; a failure fails the scheduled task.
- **Feedback loop:** thumbs up/down is also a `user_feedback` score on the turn's trace. A thumbs-down is reviewed by a person with `python -m evals.feedback` and either promoted into `evals/datasets/feedback_v1.jsonl` or dismissed, once.
- **Eval gate:** pull requests touching the answer path run the full 165-case chat_v1 set on GitHub (Eli's choice after the first gate run: the 25-case smoke subset has 1 to 4 cases per evaluator, so one answer flipped it) against a freshly ingested season, using the repository's Azure secrets (never given to forks). Thresholds are the existing `evals/thresholds.yaml`, never lowered.

## Consequences

- Langfuse adds six containers (web, worker, Postgres, ClickHouse, MinIO, Redis), only needed when tracing is wanted; the app runs without them.
- The public dashboard is a snapshot, refreshed with every Pages publish (Tuesday and Friday, or `python -m digests publish --push`).
- Promoted feedback questions become public in the repo, so promotion is a deliberate, per-question step.
- A gate run costs about $0.90 and takes 20 to 30 minutes.
