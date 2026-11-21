# 0006: Hybrid retrieval with recency

**Status:** accepted (2026-11-21)

## Context

News questions mix paraphrase ("how will the new manager set up the team") with exact tokens that embeddings handle poorly: player and club names, "matchweek 8", award names. News also goes stale within days, and the corpus is small (about 800 articles, 1500 chunks per season so far).

## Decision

Search `silver.article_chunks` two ways in Postgres: pgvector cosine distance (HNSW) and full text (`tsvector`, GIN, `websearch_to_tsquery`), each taking its top 20. Fuse them with reciprocal rank fusion (k = 60), then multiply by a recency weight `0.5 + 0.5 * 0.5^(age_days / half_life)`, half-life 14 days by default. Chunks carry a title, date and tags header, so both searches see that context. No reranker model for now.

## Consequences

- Exact-name queries and paraphrases both work. A 15-query smoke check gives hit@5 1.00 and MRR 0.76.
- RRF needs no score calibration between the two searches, and both run in the one Postgres ([ADR 0002](0002-single-postgres-store.md)).
- The recency floor of 0.5 means a much better older article can still beat a fresh weak one. The half-life is a setting (`RECENCY_HALF_LIFE_DAYS`) to tune against the Phase 3 evals.
- A cross-encoder reranker is the next step if the evals show ranking, rather than recall, is the problem.
