# Eval results

Dataset `chat_v1`, prompt `v2`, chat model `gpt-5.4-mini`, judge `gpt-5.4-mini`. Run 20261121T155251Z, eval date 2026-11-21T15:49:03.601879+00:00. Raw results: `evals/results/20261121T155251Z_chat_v1_v2.json` (not committed).

**165 cases, 79% passed.** Thresholds: all met.

Cost: chat $0.7102, judges $0.2151. Latency per case: p50 1921 ms, p95 6196 ms. Errors: 0.

## Per category

| Category | Cases | Pass rate |
|---|---|---|
| ambiguity | 6 | 100% |
| betting | 5 | 100% |
| club_info | 10 | 100% |
| comparison | 10 | 100% |
| fixtures_results | 20 | 95% |
| head_to_head | 8 | 100% |
| lineups | 6 | 67% |
| mixed_why | 12 | 0% |
| news | 26 | 35% |
| off_topic | 5 | 100% |
| player_stats | 20 | 100% |
| prompt_injection | 6 | 100% |
| standings | 15 | 100% |
| time_awareness | 10 | 80% |
| unanswerable | 6 | 100% |

## Per evaluator

| Evaluator | Applicable | Pass rate | Mean score |
|---|---|---|---|
| citation | 38 | 66% | 0.67 |
| citation_support | 26 | 46% | 0.46 |
| exact_answer | 135 | 93% | 0.94 |
| groundedness | 38 | 97% | 0.92 |
| guardrail | 30 | 97% | 0.97 |
| no_ungrounded_numbers | 91 | 99% | 1.00 |
| retrieval | 26 | 96% | 0.89 |
| tool_selection | 142 | 96% | 0.95 |

Retrieval over the news cases: hit@5 0.96, MRR 0.89.

## Worst cases

| Case | Question | Answer (start) | Failing checks |
|---|---|---|---|
| news-04 | Which assist put Declan Rice top of the Playmaker award race? | Declan Rice is top of the Playmaker race on 5 assists, but the tool data doesn’t say which specific assist was the one that moved him into first place.  What I  | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_top_scorers', 'get_player_stats']; **exact_answer**: missing facts: ['Havertz']; **citation**: no article cited |
| news-02 | Who is leading the Golden Glove race according to the Premier League? | The Golden Glove race is being led jointly by **Gabriel Magalhães (Arsenal), Bart Verbruggen (Brighton), and David Raya (Arsenal)**, each with **7 clean sheets* | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_top_scorers']; **citation**: no article cited |
| news-09 | Who won the Ballon d'Or? | I couldn’t find a Premier League article about the Ballon d’Or winner in the sources returned.  If you meant a specific player’s Ballon d’Or standing or a Premi | **exact_answer**: missing facts: ['Kane']; **citation**: no article cited |
| news-21 | What is the latest injury news at Liverpool? | The latest Liverpool injury news I could find is limited, but the key update is positive: Virgil van Dijk, Ryan Gravenberch, Jeremie Frimpong and Dominik Szobos | **citation_support**: The cited article does say Van Dijk, Gravenberch, Frimpong and Szoboszlai should all be fine, but the answer wrongly attributes this to Live; **retrieval**: expected [4764715] not in top 5 |
| news-23 | Which players visited schools for No Room For Racism? | I’m sorry, but news retrieval is unavailable right now, so I can’t verify which players visited schools for No Room For Racism. | **exact_answer**: missing facts: ['Hudson-Odoi']; **citation**: no article cited |
| news-26 | How did Arsenal get on against Hull City? | Arsenal beat Hull City 1-0 at the Emirates Stadium in matchweek 10.  If you want, I can also pull the scorers, cards, and match details. | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_head_to_head']; **citation**: no article cited |
| mixed_why-02 | Why did Man City lose at Nottingham Forest? | Man City lost at Nottingham Forest because Forest turned the game into a tight, direct contest and punished them with a big individual performance from their st | **groundedness**: 2/5: Let's think step by step: The response is grounded in the provided context in that it correctly references the available match report t; **citation_support**: The cited article only states that a former Man City striker scored twice and Forest won 3-1 to move out of the relegation zone; it does not |
| mixed_why-03 | Why did Arsenal win at Liverpool? | Arsenal won at Liverpool because they scored early and then protected the lead well.  What the match data shows: - Kai Havertz scored in the 16th minute, assist | **exact_answer**: not found: ['0, 1']; **citation**: no article cited |
| mixed_why-11 | Why are Arsenal top of the league? | Arsenal are top because they’ve started strongly and are winning the key numbers:  - **1st place** after **10 played**, with **27 points** - **Goal difference:  | **tool_selection**: missing [['search_news']]; mostly unexpected tools ['get_club_info', 'get_top_scorers', 'get_top_scorers', 'get_top_scorers']; **citation**: no article cited |
| mixed_why-12 | Why are Brighton doing so well this season? | Brighton are doing so well because they’ve combined strong results, a high goal difference, and some big individual moments.  What the data shows: - They’re **2 | **no_ungrounded_numbers**: numbers not in any tool result: ['15']; **citation_support**: The Brighton win and Gomez goal citations support those specific claims, but the answer also attributes league position, points, goal differ |

## Compared with the previous run

Comparing `evals/results/20261121T155251Z_chat_v1_v2.json` against `evals/results/20261121T154436Z_chat_v1_v1.json`.

Overall pass rate: 76% -> 79%

| Category | Before | After | Change |
|---|---|---|---|
| ambiguity | 67% | 100% | +33 pts |
| betting | 100% | 100% | +0 pts |
| club_info | 100% | 100% | +0 pts |
| comparison | 100% | 100% | +0 pts |
| fixtures_results | 85% | 95% | +10 pts |
| head_to_head | 100% | 100% | +0 pts |
| lineups | 67% | 67% | +0 pts |
| mixed_why | 0% | 0% | +0 pts |
| news | 31% | 35% | +4 pts |
| off_topic | 80% | 100% | +20 pts |
| player_stats | 100% | 100% | +0 pts |
| prompt_injection | 100% | 100% | +0 pts |
| standings | 100% | 100% | +0 pts |
| time_awareness | 80% | 80% | +0 pts |
| unanswerable | 100% | 100% | +0 pts |

| Evaluator | Before | After |
|---|---|---|
| citation | 47% | 66% |
| citation_support | 50% | 46% |
| exact_answer | 90% | 93% |
| groundedness | 95% | 97% |
| guardrail | 87% | 97% |
| no_ungrounded_numbers | 100% | 99% |
| retrieval | 96% | 96% |
| tool_selection | 88% | 96% |

Now passing (11): ambiguity-01, ambiguity-03, fixtures_results-02, fixtures_results-07, lineups-05, news-10, news-12, news-13, news-15, off_topic-02, time_awareness-03

Newly failing (5): lineups-04, news-08, news-23, news-24, time_awareness-10

## How we got here

| Run | Prompt | Dataset | Pass rate | Cost (chat + judges) |
|---|---|---|---|---|
| 1, first full run | v1 | chat_v1 as written | 76% | $0.77 |
| 2, dataset expectations corrected | v1 text | chat_v1 | 78% | $0.74 |
| 3, this report | v2 | chat_v1 | 79% | $0.93 |
| Smoke subset (25 cases) | v2 | chat_v1, tag smoke | 80% | $0.16 |

Total spent on eval runs for this phase, including two trial runs on the smoke subset: about $2.70.

**Fixed between runs**
- Prompt Shields rejected batches of more than 5 documents with a 400, so search_news failed closed (correctly) and dropped all news whenever the model asked for more than 5 results. The batching now respects both service limits (5 documents, 10,000 characters per call). This was a Phase 2 bug the evals found.
- `get_results` gained `oldest_first`, so "first match of the season" no longer returns the latest match.
- Prompt v2 (`backend/prompts/system_v2.md`): what search_news covers (referees, awards, previews, the match ball), try search_news before saying something is unavailable, cite only links search_news returned, say when no relevant article was found, never pick an ambiguous name silently, decline even quick off-topic requests, and double-check totals.
- Dataset corrections after the first run (see `evals/datasets/README.md`): `get_club_info` accepted for "next match" questions because it returns the next fixture; data tools allowed in two news questions that also ask for numbers; "Which matchweek is next?" reworded, as it was ambiguous mid-matchweek.

**Remaining failures (not hidden, not thresholded away)**
- **mixed_why 0%.** The answers explain the result correctly from match data, but the citation checks fail. The model often builds a match-centre URL itself (`/en/match/<id>`) despite the prompt, or cites nothing. And `citation_support` treats every claim in the answer as attributed to the cited article, including minutes and scorers that came from `get_match_details`. Fixing this properly means per-claim citation markers in the answer format, which belongs with the UI work in Phase 4.
- **news 35%.** The answers are mostly right, with retrieval hit@5 0.96, but `citation_support` is strict: it fails an answer if any detail goes beyond the cited chunk. A few questions are still answered from stats tools instead of search_news: the Golden Glove race, the Playmaker race, Arsenal v Hull. Some fact checks miss paraphrases: "from his own half" for "halfway", and no 96th minute.
- **Arithmetic:** "How many goals were scored in matchweek 10?" was answered as 22 from ten per-match totals that add up to 30.
- **Ambiguity:** "What was United's starting line-up last weekend?" still assumed Manchester United silently in this run (it passed in run 2).
- **Time awareness:** "results in the last matchweek" was answered with the matchweek in progress instead of the last completed one.
- **The smoke subset is below four evaluator minimums** (groundedness, retrieval, hit@5, MRR), because they are measured over only 4 to 6 cases there. It needs its own thresholds before it can gate PRs (Phase 6, CI eval gate).

Judges use the same gpt-5.4-mini deployment that answers, so they may be lenient with its style (self-preference). Set `EVAL_JUDGE_DEPLOYMENT` to a stronger model to cross-check.
