# Eval datasets

`chat_v1.jsonl`: one JSON object per case.

| Field | Meaning |
|---|---|
| `id`, `dataset`, `category` | e.g. `news-07`, `chat_v1`, `news` |
| `question`, `history` (optional) | the user turn, plus earlier turns for multi-turn cases |
| `expected_tools` | tools that must be called; a list inside the list means any of these |
| `allowed_tools` (optional) | extra tools that do not count against precision |
| `arg_checks` (optional) | `{"arg", "club_id" or "equals", "optional"}` checks on tool arguments |
| `golden` | `{"sql", "params", "match": all/any/fraction:x}` computed at eval time with `%(now)s`, or `{"articles": [content ids], "facts": [...]}` for news; `a\|b` = alternatives |
| `checks` | evaluators that apply: tool_selection, exact_answer, no_ungrounded_numbers, citation, groundedness (+ citation_support), retrieval, guardrail |
| `rubric` (optional) | what the guardrail judge passes or fails |
| `inject_chunks` (optional) | fake article chunks planted in front of the real search results |
| `tags` | `smoke` marks the 25-case subset |

Categories in chat_v1: standings 15, fixtures_results 20, player_stats 20, comparison 10, club_info 10, head_to_head 8, lineups 6, news 26, mixed_why 12, time_awareness 10, ambiguity 6, unanswerable 6, off_topic 5, betting 5, prompt_injection 6 (165).

## CHANGELOG

- **chat_v1** (2026-11-21): first version, 165 cases. After the first calibration run (before thresholds were set), these expectations were corrected because they were wrong, not because the model failed them:
  - "next match" questions also accept `get_club_info`, which returns the next fixture;
  - news-01 and news-25 allow data tools, because those questions also ask for numbers;
  - lineups-05 accepts `get_fixtures` (an upcoming line-up is known to be unpublished);
  - time_awareness-03 was reworded ("Which matchweek is the next Premier League match part of?") because "which matchweek is next" is ambiguous mid-matchweek.

New cases or changed goldens go into a new file (`chat_v2.jsonl`) with an entry here, so results stay comparable within one version.
