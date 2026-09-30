# Decisions log

## Three-stage matching, LLM only for ambiguous rows
Exact code match (verified by name), then confident fuzzy match, then LLM. Most rows are resolved deterministically, which keeps the pipeline fast, cheap, and auditable. The LLM handles only the rows that need judgment.

## Exact code matches are checked against the name
A naive code lookup would accept the planted swapped-code row, where the code belongs to a different real item. The tool only trusts a code match if the names agree and no other item fits the name better.

## Conflicts are flagged and never auto-resolved
When two systems disagree on cost or work centre, the tool cannot know which is right. That is a business decision, so conflicts go to a human review queue.

## Fixed response parsing for thinking blocks
First AI run failed because the model's reply began with a thinking block, and the code assumed the first block was the text answer. Changed the parser to keep only text blocks and extract the JSON object, and raised max_tokens from 200 to 2000 so the model has room to reason and still answer.

## First AI run (seed 42)
Baseline 91/101 (90%) with 3 confident wrong matches and 37 review items. With AI: 101/101 (100%), 0 wrong matches, 12 review items, all real planted problems. 4 answers at medium confidence, all correct, all name-only matches with no code corroboration.

## Held-out test (seed 7)
Concern: the thresholds were set while looking at the seed 42 data, so 100% might reflect tuning rather than generalization. Generated a new dataset with seed 7 and reran everything with no code changes. Baseline 95/101 (94%), 24 review items. With AI: 101/101 (100%), 0 wrong matches, 12 review items, all real. 5 medium-confidence answers, all correct, same pattern as before. Result held.

## Kept medium-confidence answers as accepted
I considered accepting only high confidence. All 9 medium answers across both runs were correct, and rejecting them would add 4 to 5 rows per run to the review queue for no accuracy gain. On real data with less predictable abbreviations, high-only would be the safer starting point.
