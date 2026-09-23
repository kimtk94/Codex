# Kalman R9-NG — Historical GDELT Web NGram Readiness

**Pre-registered:** 2026-09-23
**Mode:** RESEARCH_ONLY
**Champion:** R5.1_BASE_HGB
**Production/LIVE:** unchanged

## 1. Source decision

GDELT legacy DOC API returned explicit HTTP 429 responses instructing high-traffic users to move to the Web NGrams dataset.

Historical R9 therefore stops using DOC ArticleList / Timeline endpoints for bulk retrieval.

Primary source:
- BigQuery public dataset
- `gdelt-bq.gdeltv2.web_1grams`
- `gdelt-bq.gdeltv2.web_2grams`

Historical window:
- 2023-07-01 00:00:00 UTC inclusive
- 2026-09-02 00:00:00 UTC exclusive

Language:
- ENGLISH

## 2. Information represented

R9-NG measures **company-name mention intensity**, not distinct article count.

For each symbol and UTC day:
- `mention_count` = sum of GDELT NGram COUNT for the frozen alias
- absent symbol/day = zero mentions after calendar completion

This is deliberately lower-dimensional than article-level sentiment or event classification.

## 3. Alias contract

Ticker-only search is prohibited.

Each symbol gets one frozen public-company alias derived from the R8 SEC registry.

Only 1-token and 2-token aliases are admitted to the initial BigQuery path because they can be matched directly against Web 1Gram / 2Gram tables without regex scanning the much larger Web NGrams 3.0 context table.

Known public-name overrides include:
- AAPL -> Apple Inc
- MSFT -> Microsoft
- NVDA -> NVIDIA
- AMZN -> Amazon
- META -> Meta Platforms
- GOOG/GOOGL -> Alphabet
- JPM -> JPMorgan Chase
- XOM -> ExxonMobil
- WMT -> Walmart
- UNH -> UnitedHealth Group

Any >2-token alias is `NEEDS_OVERRIDE` and is excluded until a <=2-token public alias is frozen.
Alias overrides may be added only for data identity/readiness and before any R9 alpha fitting.

## 4. PIT contract

Raw GDELT Web NGram DATE has 15-minute timestamps.

R9-NG is collapsed to UTC daily mention counts.

For any R5 hourly signal at `signal_as_of`:
- only completed UTC days strictly earlier than `DATE(signal_as_of)` are available;
- same-UTC-day mention counts are forbidden.

Thus later coverage from the signal day cannot leak into that signal.

## 5. Query governance

A BigQuery **dry-run is mandatory** before execution.

Default runner:
- generates frozen alias registry and SQL;
- performs BigQuery dry-run;
- reports bytes to be processed;
- does not execute the query.

Actual query requires explicit:
- `R9_NGRAM_EXECUTE=YES`

The query is restricted by:
- GDELT DATE numeric range
- LANG='ENGLISH'
- exact LOWER(NGRAM) equality against frozen 1- or 2-token aliases

No regex scan over the full Web NGrams 3.0 table is allowed in R9-NG v1.

## 6. Readiness gates

Before model fitting:
- frozen universe = 93 symbols
- >= 90 / 93 symbols have a supported 1-2 token alias
- BigQuery dry-run succeeds
- actual query succeeds
- >= 80 symbols have at least one historical mention
- global usable span >= 24 months
- duplicate symbol + UTC date rows = 0
- all mention_count values finite and >= 0
- no production writes

If passed:
- `next_action = PREREGISTER_SINGLE_R9_NGRAM_ABLATION`

## 7. Production invariant

R9-NG does not alter:
- R5.1 scoring
- LIVE orders
- sizing
- exits
- strategy_signal
- R5-EXIT-V1
- R8 passive risk work
