# Eval results

Dataset `chat_v1`, prompt `v3`, chat model `gpt-5.4-mini`, judge `gpt-5.4-mini`. Run 20261121T161838Z, eval date 2026-11-21T16:15:37.469801+00:00. Raw results: `evals/results/20261121T161838Z_chat_v1_v3.json` (not committed).

**165 cases, 82% passed.** Thresholds: **below threshold:** evaluator exact_answer 0.896 < 0.9; evaluator tool_selection 0.944 < 0.95; category ambiguity 0.667 < 0.8

Cost: chat $0.6488, judges $0.1751. Latency per case: p50 2081 ms, p95 4316 ms. Errors: 1.

## Per category

| Category | Cases | Pass rate |
|---|---|---|
| ambiguity | 6 | 67% |
| betting | 5 | 100% |
| club_info | 10 | 100% |
| comparison | 10 | 100% |
| fixtures_results | 20 | 85% |
| head_to_head | 8 | 100% |
| lineups | 6 | 83% |
| mixed_why | 12 | 58% |
| news | 26 | 46% |
| off_topic | 5 | 80% |
| player_stats | 20 | 100% |
| prompt_injection | 6 | 100% |
| standings | 15 | 93% |
| time_awareness | 10 | 80% |
| unanswerable | 6 | 100% |

## Per evaluator

| Evaluator | Applicable | Pass rate | Mean score |
|---|---|---|---|
| citation | 38 | 79% | 0.88 |
| citation_support | 22 | 73% | 0.73 |
| exact_answer | 135 | 90% | 0.91 |
| groundedness | 38 | 100% | 0.92 |
| guardrail | 29 | 93% | 0.93 |
| no_ungrounded_numbers | 91 | 99% | 0.99 |
| retrieval | 26 | 96% | 0.89 |
| tool_selection | 142 | 94% | 0.92 |

Retrieval over the news cases: hit@5 0.96, MRR 0.89.

## Worst cases

| Case | Question | Answer (start) | Failing checks |
|---|---|---|---|
| news-04 | Which assist put Declan Rice top of the Playmaker award race? | Declan Rice is top of the Playmaker race with 5 assists [1]. | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_top_scorers']; **exact_answer**: missing facts: ['Havertz']; **citation**: none of the expected articles [4737173] cited (cited []); news answer cites no article |
| news-09 | Who won the Ballon d'Or? | The Premier League article I found is about the Golden Boot and Golden Glove, not the Ballon d’Or [1][2]. I don’t have a Ballon d’Or winner in the available Pre | **exact_answer**: missing facts: ['Kane']; **citation**: none of the expected articles [4749936] cited (cited ['a4737300', 'a4737165']); **citation_support**: The cited articles only discuss the Premier League Golden Boot and Golden Glove, and do not support any claim about Ballon d’Or coverage or  |
| news-16 | How did Haaland do for Norway in the international break? | I can give you his Premier League season stats, but I can’t tell how Haaland did for Norway in the international break from the data available here. His season  | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_player_stats']; **exact_answer**: missing facts: ['Denmark', '96']; **citation**: none of the expected articles [4763580] cited (cited []); news answer cites no article |
| news-01 | How does Arsenal's start compare with the best ever Premier League starts? | Arsenal’s start is excellent, but I can’t fairly compare it to the **best ever Premier League starts** from the data I have here, because I only have the curren | **tool_selection**: missing [['search_news']]; **citation**: none of the expected articles [4762992] cited (cited []); news answer cites no article |
| news-02 | Who is leading the Golden Glove race according to the Premier League? | Gabriel Magalhães, Bart Verbruggen and David Raya are currently tied for the Golden Glove lead with 7 clean sheets each [1]. | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_top_scorers']; **citation**: none of the expected articles [4737165] cited (cited []); news answer cites no article |
| news-20 | What are some memorable moments from Liverpool v Man Utd? | This season’s Liverpool v Manchester United meetings are both still to be played, so there aren’t any 2026-27 match highlights to recall yet [1][2].  If you wan | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_head_to_head']; **citation**: none of the expected articles [4214335] cited (cited []); news answer cites no article |
| news-25 | What did we learn from Man Utd's defeat to Bournemouth? | I couldn’t find a relevant official Premier League “what we learned” article about Man Utd’s defeat to Bournemouth in the news results I searched.  If you want, | **exact_answer**: missing facts: ['Fernandes']; **citation**: nothing cited |
| news-26 | How did Arsenal get on against Hull City? | Arsenal beat Hull City 1-0 at the Emirates Stadium [1]. | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_results']; **citation**: none of the expected articles [4757016] cited (cited []); news answer cites no article |
| mixed_why-06 | Why did Newcastle lose to Everton? | Newcastle lost because Everton scored early in the second half and then protected the lead well. Thierno Barry’s goal in the 49th minute was the only goal [1].  | **exact_answer**: not found: ['0, 1']; **citation_support**: Article [2] supports that Joelinton was out, Jacob Ramsey returned from suspension, and Yoane Wissa was an option from the bench, but it doe |
| standings-15 | How many league games have Spurs won this season? | Spurs have won 3 league games this season [1]. | **no_ungrounded_numbers**: numbers not in any tool result: ['3'] |

## Compared with the previous run

Comparing `evals/results/20261121T161838Z_chat_v1_v3.json` against `evals/results/20261121T155251Z_chat_v1_v2.json`.

Overall pass rate: 79% -> 82%

| Category | Before | After | Change |
|---|---|---|---|
| ambiguity | 100% | 67% | -33 pts |
| betting | 100% | 100% | +0 pts |
| club_info | 100% | 100% | +0 pts |
| comparison | 100% | 100% | +0 pts |
| fixtures_results | 95% | 85% | -10 pts |
| head_to_head | 100% | 100% | +0 pts |
| lineups | 67% | 83% | +17 pts |
| mixed_why | 0% | 58% | +58 pts |
| news | 35% | 46% | +12 pts |
| off_topic | 100% | 80% | -20 pts |
| player_stats | 100% | 100% | +0 pts |
| prompt_injection | 100% | 100% | +0 pts |
| standings | 100% | 93% | -7 pts |
| time_awareness | 80% | 80% | +0 pts |
| unanswerable | 100% | 100% | +0 pts |

| Evaluator | Before | After |
|---|---|---|
| citation | 66% | 79% |
| citation_support | 46% | 73% |
| exact_answer | 93% | 90% |
| groundedness | 97% | 100% |
| guardrail | 97% | 93% |
| no_ungrounded_numbers | 99% | 99% |
| retrieval | 96% | 96% |
| tool_selection | 96% | 94% |

Now passing (12): lineups-06, mixed_why-01, mixed_why-02, mixed_why-03, mixed_why-04, mixed_why-05, mixed_why-07, mixed_why-08, news-11, news-17, news-23, news-24

Newly failing (7): ambiguity-01, ambiguity-06, fixtures_results-01, fixtures_results-07, news-15, off_topic-02, standings-15
