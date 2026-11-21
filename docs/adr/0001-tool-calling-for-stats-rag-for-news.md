# 0001: Tool calling for stats, RAG for news

**Status:** accepted (2026-11-21)

## Context

Users ask two kinds of questions: factual ones (scores, table positions, dates, player stats) that must be exact and current, and news ones (injuries, previews, features) answered by prose. LLMs hallucinate numbers, and retrieved prose often contains stale numbers.

## Decision

Stats are answered only through tool calls that query structured data in Postgres. RAG is used for articles only, and the model never states a score, position, date or stat that did not come from a tool call. News answers cite title, date and URL.

## Consequences

- Needs a well-designed set of tools over gold tables, and evals that check numbers come from tools.
- Mixed questions take both paths in one turn.
- Retrieved text needs Prompt Shields because it is untrusted input.
