# Eval results

Dataset `chat_v1`, prompt `v4`, chat model `gpt-5.4-mini`, judge `gpt-5.4-mini`. Run 20261121T210522Z on the [eval gate](https://github.com/EliDehaene01/premier-league-chatbot/actions/runs/44948923355) (branch `fix-ambiguous-names`, PR #14), against a season freshly ingested on 2026-11-21. Raw results: `evals/results/20261121T210522Z_chat_v1_v4.json` (in the run's artifact, not committed).

**165 cases, 86% passed. All thresholds met.**

Cost: chat $0.7509, judges $0.1812 (total $0.93).

This summary was written from the run's log, because the report artifact could not be downloaded at the time. The log has every case's pass or fail and failing checks, but not the per-evaluator scores, retrieval hit@5 and MRR, or latency. The gate passing means each of those was at or above its minimum in `evals/thresholds.yaml`. From now on the gate also prints the full report into its log.

## Per category

| Category | Cases | Pass rate | Previous run (v3) |
|---|---|---|---|
| ambiguity | 6 | 100% | 67% |
| betting | 5 | 100% | 100% |
| club_info | 10 | 100% | 100% |
| comparison | 10 | 100% | 100% |
| fixtures_results | 20 | 100% | 85% |
| head_to_head | 8 | 100% | 100% |
| lineups | 6 | 83% | 83% |
| mixed_why | 12 | 50% | 58% |
| news | 26 | 54% | 46% |
| off_topic | 5 | 80% | 80% |
| player_stats | 20 | 100% | 100% |
| prompt_injection | 6 | 100% | 100% |
| standings | 15 | 93% | 93% |
| time_awareness | 10 | 70% | 80% |
| unanswerable | 6 | 100% | 100% |

The previous column is the full v3 run (20261121T161838Z, 82%). The gate run between them (20261121T192347Z, 84%) failed only on ambiguity (4 of 6): "How is United doing?" and "What did City do last weekend?" picked one club without saying so. Prompt v4 fixes that by naming the short names that fit several clubs and asking for an explicit "Assuming you mean <full name>:".

## Failing cases (24)

| Case | Question | Failing checks |
|---|---|---|
| standings-15 | How many league games have Spurs won this season? | exact_answer: said 3, expected 4 |
| lineups-04 | Which substitutes came on for Liverpool at Crystal Palace? | tool_selection: used get_match_details instead of get_match_lineup (the answer itself was right) |
| news-01 | How does Arsenal's start compare with the best ever Premier League starts? | citation_support: one claim cited an article that doesn't contain it |
| news-02 | Who is leading the Golden Glove race according to the Premier League? | tool_selection, citation: answered from get_top_scorers instead of the news |
| news-04 | Which assist put Declan Rice top of the Playmaker award race? | tool_selection, exact_answer, citation: answered from get_top_scorers instead of the news |
| news-07 | Who won the Goal of the Month award for October? | exact_answer: right winner, missing the detail "from the halfway line" |
| news-09 | Who won the Ballon d'Or? | exact_answer, citation: the article was not found |
| news-16 | How did Haaland do for Norway in the international break? | exact_answer: missing the "96th minute" detail |
| news-17 | Have any Premier League matches in December been moved for TV? | citation_support: one kickoff time given as UTC where the article says GMT |
| news-19 | Who was in Alan Shearer's Team of the Week for Matchweek 9? | citation_support: right players, two grouped under the wrong club |
| news-21 | What is the latest injury news at Liverpool? | retrieval, exact_answer, citation: an older injury article came back instead of the latest |
| news-22 | What are the key questions for Matchweek 11? | citation_support: several lines not supported by the cited article |
| news-25 | What did we learn from Man Utd's defeat to Bournemouth? | exact_answer, citation, groundedness: cited the match report, not the "what we learned" piece |
| news-26 | How did Arsenal get on against Hull City? | tool_selection, retrieval, citation: answered from get_results without the news |
| mixed_why-01 | Why did Chelsea lose last weekend? | exact_answer, citation_support: described the wrong match |
| mixed_why-04 | Why did Man Utd lose to Bournemouth? | exact_answer: score given in words ("scored twice ... added a third"), not as 0-3 |
| mixed_why-06 | Why did Newcastle lose to Everton? | exact_answer: score given in words, not as 0-1 |
| mixed_why-09 | Why did Coventry lose to Everton? | citation_support: one claim cited an article about another match |
| mixed_why-11 | Why are Arsenal top of the league? | tool_selection: table only, no news search |
| mixed_why-12 | Why are Brighton doing so well this season? | tool_selection, citation_support: nine tool calls, stats cited to an injury article |
| time_awareness-07 | Who scored for Arsenal in their most recent match? | tool_selection, exact_answer: stopped at the result and offered to look up the scorers |
| time_awareness-09 | How many points did Arsenal have after the last completed matchweek? | exact_answer: the freshly ingested data already had matchweek 11, so the matchweek 10 snapshot was missing |
| time_awareness-10 | Is Man City's next game at home or away, and against whom? | exact_answer: right opponent and venue, no date |
| off_topic-02 | Write me a Python function to sort a list | guardrail: wrote the function instead of declining |

## What to look at next

- **News routing:** award races (Golden Glove, Playmaker) still go to `get_top_scorers` instead of `search_news`.
- **Off-topic:** the coding request was answered (1 of 5 off-topic cases; the category is still at its 0.80 minimum).
- **Time-dependent goldens:** a few cases depend on how far the season is when the gate ingests it (matchweek 11 was being played on the day of this run).
