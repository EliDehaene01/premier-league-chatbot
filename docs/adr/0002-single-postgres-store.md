# 0002: One Postgres store for data and vectors

**Status:** accepted (2026-11-21)

## Context

We need relational storage for matches, standings and players, raw storage for API responses, and vector search for article chunks. Data volume is small: one season.

## Decision

One Postgres 16 instance with pgvector (`pgvector/pgvector:pg16` in docker compose), with schemas `bronze`, `silver` and `gold`. Credentials come only from `.env`.

## Consequences

- One service to run and back up; joins between vectors and metadata (date, club) are plain SQL.
- pgvector is enough at this scale; a dedicated vector DB would be revisited only if it is not.
