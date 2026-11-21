# 0012: Local-first, on Azure OpenAI through Microsoft Foundry

**Status:** accepted (2026-11-21)

## Context

The chatbot needs a database, a backend, a UI, a language model and an embedding model. It is a personal project on a small budget. Hosting a database and an API around the clock would cost more than the model calls do. The model calls also need a provider with content-safety tooling for the third-party article text that ends up in prompts.

## Decision

- **Everything runs locally**: Postgres in Docker, the Python backend, the React UI and the scheduled jobs (Windows Task Scheduler). Nothing is deployed.
- **Only static output is public:** the weekly summaries, the showcase and the AI Ops totals on GitHub Pages ([ADR 0009](0009-digests-on-github-pages.md), [ADR 0011](0011-ai-ops.md)).
- **The model layer is Azure OpenAI through Microsoft Foundry:**
  - chat model `gpt-5.4-mini`, chosen over gpt-4.1-mini;
  - embedding model `text-embedding-3-small`;
  - Azure AI Content Safety Prompt Shields for retrieved text.
- **No Foundry agent features:** no Foundry web search or Foundry-side tools. The data comes from our own tools, and the system prompt lives versioned in the repo (`backend/prompts/`), not in the Foundry playground.
- **Model calls are written behind an `LLMProvider` interface**, so tests use a scripted fake and another provider could be swapped in.

## Consequences

- Running costs are only the model calls: under a cent per chat answer, about $0.90 for a full eval run. These show on the AI Ops page.
- Anyone who wants to run it needs Docker and their own Azure keys. The README walks through both.
- The scheduled jobs need the laptop to be on (Task Scheduler catches up missed runs).
- The eval gate on GitHub uses repository secrets. It starts only when the owner runs it by hand, so neither outsiders nor repeated pushes can spend the budget.
