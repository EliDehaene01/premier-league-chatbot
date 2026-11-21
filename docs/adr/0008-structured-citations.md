# 0008: Structured citations

**Status:** accepted (2026-11-21)

## Context

Phase 3 evals showed citations were the weakest part of the answers: on "why" questions the model built its own match links, cited loosely related articles or cited nothing (why-questions 0%, citations valid 66%). Free-text "title, date, URL" citations cannot be checked reliably, and a model-written URL can be wrong or invented. The UI also needs to link each claim to its source.

## Decision

- Every tool result carries short `source_id`s (`a`, `m`, `t`, `s`, `c` plus an id). The prompt (v3) asks for the id in square brackets right after the fact it supports, and forbids URLs and sources sections.
- The backend owns the citation: `backend/llm/citations.py` keeps only ids a tool returned in this turn, resolves them to title, date and URL from the database, and renumbers them `[1]`, `[2]`. Unknown ids are dropped and counted.
- The API returns the answer and the `sources` list together; the UI renders `[n]` as links to source cards.

## Consequences

- URLs come from our data, never from the model, so a link cannot be invented.
- Every number in an answer can point at the tool result behind it, which the evals can check in code.
- The CLAUDE.md rule "every news answer cites title, date and URL" is now met by the source cards rather than by text in the answer.
- Evals v3 against Phase 3: why-questions 0% to 58%, citations valid 66% to 79%, cited article supports the claim 46% to 73%.
