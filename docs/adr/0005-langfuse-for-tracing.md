# 0005: Langfuse for tracing

**Status:** accepted (2026-11-21)

## Context

We need traces of each chat turn (prompts, tool calls, retrieval, latency, token cost) for debugging, evals and an ops dashboard, while everything runs locally.

## Decision

Self-hosted Langfuse, added in Phase 6, running beside Postgres in docker compose. How it is used: [ADR 0011](0011-ai-ops.md).

## Consequences

- No traces leave the machine; one more service to run.
- Cost and latency dashboards and the feedback loop build on Langfuse data.
