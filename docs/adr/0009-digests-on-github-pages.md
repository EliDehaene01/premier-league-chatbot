# 0009: Weekly digests: facts first, validated, published to a gh-pages branch

**Status:** accepted (2026-11-21)

## Context

The Tuesday recap and Friday highlights must be generated from stored data only, cite their sources, rank news with fixed weights (CLAUDE.md), and be readable by anyone on GitHub Pages. The chatbot itself runs only on the laptop, which also holds the database and the Azure keys, so that is where the digests are written. The repo is public so that Pages is free.

## Decision

- **Facts first:** code gathers every fact with its source_id; one structured-output call per document writes prose around them. The results list and the table are rendered by code.
- **Validate, don't trust:** lines whose sources are unknown, or whose numbers or scores are not in their sources, are dropped and logged. The recap retries once.
- **Ranking in config:** the model only labels a story's type; the score comes from `digests/weights.yaml`.
- **Static site on `gh-pages`:** a Python renderer (no site generator, no Node build) writes plain HTML into a worktree of an orphan `gh-pages` branch and pushes it. Pages serves the branch directly, with no Actions workflow.

## Consequences

- The model cannot drop a fixture or misreport a score in the results; its errors cost lines, not correctness.
- Publishing never switches or dirties the branch checked out on the laptop, and the site's history stays out of main.
- The laptop must be on (or catch up with StartWhenAvailable) and have push access; a missed run shows as a stale "This week".
- A plain renderer keeps the site dependency-free; anything richer (search, feeds) would justify a generator later.
