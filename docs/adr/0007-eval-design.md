# 0007: Eval design

**Status:** accepted (2026-11-21)

## Context

Changes to prompts, tools, retrieval and the model need a measurable gate (see CLAUDE.md). The data changes every week, so hard-coded expected answers would rot within days. News answers have no single correct string, and a few behaviours (declining, handling ambiguity, resisting injected text) can only be judged by reading the answer.

## Decision

- **One versioned JSONL dataset per surface** (`evals/datasets/chat_v1.jsonl`), with categories that mirror what users ask, a smoke tag for a cheap subset, and a CHANGELOG.
- **Goldens as queries, not values:** data cases carry SQL over gold and silver, run at eval time against an eval date the runner also passes to the chat loop. News cases are pinned to dated articles with required facts.
- **Code checks first** (tool selection with argument checks, exact values, no ungrounded numbers, citation validity, retrieval hit@5 and MRR). **LLM judges only where code cannot decide:** groundedness via azure-ai-evaluation, citation support, and per-case guardrail rubrics. The judge deployment is a setting, so a stronger model can grade.
- **The real pipeline under test:** real tools, the real database, real Prompt Shields. Injection cases plant text in front of real retrieval results.
- **Thresholds from measurement:** each is set to the measured score minus one case of slack, never above what we achieve, and never lowered to get green. Results files stay out of git; the readable summary (`docs/EVAL_RESULTS.md`) is committed.

## Consequences

- The dataset stays valid as the season moves. Re-running it on another day tests the same behaviour against new numbers.
- Judges sharing the answering model may be lenient with its style; code checks carry most of the weight, and the judge can be swapped.
- A full run costs about $1 and takes about 4 minutes. The smoke subset costs about $0.15 but is too small for per-evaluator thresholds; it needs its own before it gates PRs in CI (Phase 6).
- Strict citation checks expose that answers mix data and article claims without per-claim markers. That is a product change (Phase 4 UI), not a reason to loosen the check.
