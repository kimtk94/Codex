# Kalman R9-T — Historical News Timeline Readiness

**Pre-registered:** 2026-09-23
**Mode:** RESEARCH_ONLY
**Champion:** R5.1_BASE_HGB
**Production/LIVE:** unchanged

## 1. Why R9-T

R9 ArticleList smoke established:
- company alias mapping works,
- GDELT returns symbol-specific coverage,
- GDELT seendate and URLs are structurally usable,
- but ArticleList is rate-limited and capped at 250 records.

ArticleList is therefore not approved for multi-year historical backfill.

R9-T uses GDELT DOC 2.0 `TimelineVolRaw` for historical **news intensity** only.

## 2. Source contract

Endpoint:
- GDELT DOC 2.0

Mode:
- `timelinevolraw`

Query:
- exact frozen public company alias
- `sourcelang:english`
- ticker-only queries prohibited

Historical window:
- 2023-07-01 00:00:00 UTC
- through 2026-09-02 00:00:00 UTC

The end is intentionally midnight UTC. The R5 cutoff day is not consumed as a completed daily news observation.

## 3. Timeline fields

For every returned timeline point store:

- symbol
- company_name
- query_alias
- date_utc
- matched_articles
- monitored_articles
- coverage_share = matched_articles / monitored_articles
- gdelt_series
- source = GDELT_DOC_2_TIMELINEVOLRAW

No article URLs, sentiment, tone, direction, LLM classification, or price reaction are used in R9-T readiness.

## 4. Point-in-time rule

Long-horizon TimelineVolRaw queries resolve to daily observations.

For an hourly R5 signal at `signal_as_of`:
- only timeline dates **strictly earlier than the UTC calendar date containing signal_as_of** may be used;
- the current UTC day's timeline value is forbidden;
- this ensures later articles from the same UTC day cannot leak into the signal.

This contract is frozen before any R9-T model fitting.

## 5. Request policy

- one root TimelineVolRaw request per symbol for the full historical window;
- successful responses are cached;
- default minimum request spacing = 12 seconds;
- transient 429/5xx retry only;
- default max retries = 2;
- no recursive window splitting;
- no ArticleList MAXRECORDS parameter.

## 6. Smoke

Deterministic 10-symbol set:
AAPL, MSFT, NVDA, AMZN, META, GOOG, JPM, XOM, WMT, UNH.

Smoke passes only if:
- request success >= 90%;
- timeline parse success >= 90%;
- >= 9/10 symbols have at least 300 timeline points;
- monitored_articles > 0 for >= 99% of parsed rows;
- zero duplicate symbol + date rows.

## 7. Full readiness gates

All required:
- frozen universe = 93;
- request success >= 90%;
- parsed timeline success >= 90%;
- >= 80 / 93 symbols have at least 700 daily timeline points;
- usable global span >= 24 months;
- monitored_articles > 0 ratio >= 99%;
- finite coverage_share ratio >= 99%;
- duplicate symbol + date ratio = 0;
- production_changed = false;
- model_fitting_allowed = false during readiness.

If all pass:
- `next_action = PREREGISTER_SINGLE_R9_TIMELINE_ABLATION`

No R9 alpha result is inspected in readiness.

## 8. Production invariant

R9-T does not alter:
- R5.1 scoring
- orders
- sizing
- exits
- strategy_signal
- R5-EXIT-V1
- R8 risk ledger
