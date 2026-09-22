# Kalman R9-N — Symbol-Specific News PIT Readiness

**Pre-registered:** 2026-09-22
**Mode:** RESEARCH_ONLY
**Champion:** R5.1_BASE_HGB
**Production/LIVE:** unchanged

## 1. Motivation

R7-M macro and R8C1 SEC-event recency did not beat frozen R5.1 on the alpha-promotion gates.

R9-N opens a genuinely different information axis:
**symbol-specific external news observed by GDELT**, rather than global macro state or SEC filing presence.

No R9-N alpha model is fit in this stage.

## 2. Source

Primary historical source:
- GDELT DOC 2.0 API
- article-list JSON
- exact company-name phrase queries
- no API key

Timestamp contract:
- `seendate` is treated as `available_at`
- `time_quality = GDELT_SEENDATE_OBSERVED_PROXY`
- publication timestamps inferred from article pages are not used
- no article can affect a signal before `available_at <= signal_as_of`

## 3. Frozen universe and alias contract

Universe:
- frozen R5 93-symbol universe from R8 SEC v2 registry

Alias seed:
- SEC company_name attached to R8-S events
- normalized public company phrase
- frozen overrides for legally awkward/current-successor names (for example Amazon, JPMorgan Chase, ExxonMobil)
- no ticker-only search

This explicitly avoids ambiguous ticker strings such as:
- C
- T
- CAT
- LOW
- DE

Multiple traded share classes of the same issuer may share the same news article.

## 4. Query contract

DOC 2.0 validation window:
- 2026-06-23 through 2026-09-02 13:30 UTC
- chosen to remain inside DOC 2.0's documented recent-three-month explicit date-window limit at preregistration time

Query granularity:
- calendar-month windows
- each symbol/company alias queried independently
- maxrecords=250 per request
- if a month reaches the 250-record ceiling, that month is marked `SATURATED` and is not silently treated as complete

The DOC API is not used for a 2023-2026 historical backfill because its official STARTDATETIME/ENDDATETIME contract only supports the recent three-month window.

Only English-language articles are retained in v1.

## 5. Canonicalization and dedupe

Article identity:
- canonical URL normalized by stripping URL fragment and common tracking parameters
- per-symbol uniqueness key = `symbol + canonical_url`
- first observed `seendate` wins

Cross-symbol duplicate URLs are allowed because one article can refer to multiple traded share classes.

No article text is fetched in R9.0.

## 6. R9.0 stored fields

- symbol
- company_name
- query_alias
- canonical_url
- title
- domain
- language
- sourcecountry
- available_at
- time_quality
- gdelt_raw_seendate
- query_window_start
- query_window_end
- query_saturated
- article_id

No sentiment, direction, novelty, LLM classification, or price reaction is computed in R9.0.

## 7. Readiness gates

All required:
- frozen universe = 93 symbols
- >= 80 / 93 symbols with at least 10 mapped recent articles
- >= 60 days usable span
- >= 95% rows with parseable GDELT seendate
- >= 95% rows with canonical URL
- within-symbol duplicate ratio <= 5%
- saturated symbol-month windows <= 5% of all successful symbol-month queries
- >= 5,000 deduplicated symbol-article rows
- no production writes
- no model fitting

If saturation is too high, the only permitted fix is narrower date windows. Alias expansion is a separate preregistration.

## 8. Smoke gate

Before full backfill:
- 10 deterministic symbols
- August 2026 only
- same alias/query/dedupe contract

Smoke passes when:
- HTTP success >= 90%
- >= 7 / 10 symbols return at least one article
- >= 90% returned rows have parseable seendate
- zero production changes

## 9. Future R9.1

R9.1 is NOT admitted by this spec.

If recent R9.0 readiness passes, R9-N moves to a prospective news ledger first. Historical R9 alpha promotion is not allowed from DOC 2.0 because the required multi-year PIT backfill is unavailable through this API.

A future alpha challenger requires a separately preregistered prospective evaluation or a separately validated historical raw/BigQuery data source.

Candidate feature family may include only:
- recent article count
- time-decayed article count
- title-level novelty using a stateless hashing representation
- deterministic event-category flags if separately frozen before performance inspection

No retrospective feature search on E2-E8 is allowed.

## 10. Production invariant

R9-N:
- does not alter R5.1
- does not alter LIVE orders
- does not alter sizing
- does not alter exits
- does not write strategy_signal
- does not modify R5-EXIT-V1


## 11. Smoke result and source-contract correction

First smoke observed:
- 10 symbol queries
- 1 HTTP success / 9 HTTP 429
- NVDA returned 201 rows
- seendate parse ratio 100% on successful rows
- canonical URL ratio 100% on successful rows
- production unchanged

This is a source-access/readiness failure, not an alpha result.

The following changes are frozen before rerun:
- minimum request interval: 8 seconds
- HTTP 429 adaptive backoff: 10s, 20s, 40s, 80s (or Retry-After if provided)
- maximum 4 retries
- public-name alias normalization
- modes are now `smoke` and `recent`; multi-year `full` mode is prohibited for DOC 2.0

No model fitting is enabled by these changes.
