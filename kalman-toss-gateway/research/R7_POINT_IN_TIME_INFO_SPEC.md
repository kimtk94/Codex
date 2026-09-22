# Kalman R7 — Point-in-Time Information Layer

**Status:** RESEARCH_ONLY / PRE-REGISTERED READINESS STAGE  
**Date:** 2026-09-22  
**Production/LIVE:** unchanged  
**Champion:** R5.1_BASE_HGB remains untouched

## 1. Why R7 exists

R6 selective/meta filters and R6.1 target redesign did not beat the frozen R5 cross-sectional relative-return HGB baseline. R7 therefore does not retune R5 thresholds or targets. It adds genuinely new information domains with strict point-in-time semantics.

R7 is split into:

1. **R7.0 Data Readiness** — no model fitting, no performance selection.
2. **R7.1 Bounded Information-Axis Ablation** — only axes that pass R7.0 may enter.
3. **R7.2 Prospective shadow** — only if an R7.1 challenger survives frozen statistical and execution gates.

No forced winner.

## 2. Current observed state at R7 creation

Neon currently contains:

- macro_release_observation: 0 rows
- macro_policy_repricing_observation: 0 rows
- macro_shadow_evaluation_v1: 4 rows
- news_article: 839 rows
- news_event: 839 rows
- news_feature_snapshot: 173 rows
- news_coverage_hourly: 13 rows
- news_entity: 839 mappings but only 9 distinct symbolic buckets; most are GLOBAL/US_NEWS/KR_MACRO rather than stock symbols
- symbol-level news feature snapshots: effectively unavailable for the 93-stock R5 universe
- analyst earnings-revision point-in-time history: not yet contracted

Therefore R7.1 is blocked until readiness gates pass.

## 3. R7 information axes

### M — Macro release / surprise / rates reaction

Core event families:
- CPI / Core CPI
- PCE / Core PCE
- NFP / unemployment / average hourly earnings
- PPI
- Retail Sales
- ISM Manufacturing / Services
- JOLTS
- Initial Jobless Claims
- FOMC decision / statement / dot plot when available

Required point-in-time fields:
- event identifier
- release_at
- available_at
- actual
- consensus when licensed/available
- previous and revision state
- source
- time_quality

Derived features must be computed only from information with available_at <= signal_as_of.

Candidate feature families:
- standardized surprise = (actual - consensus) / historical surprise scale
- directionally signed inflation/growth/labor surprise
- event-family decay
- US 2Y reaction around event
- policy-repricing confirmation
- surprise × US2Y reaction interaction

Free-data mode may use official release timestamps/actuals and market reaction, but must not fabricate consensus.

### N — Symbol-level news

Required raw contract:
- published_at
- first_seen_at
- available_at
- source
- canonical URL/hash for dedupe
- symbol mapping with relevance
- event type
- sentiment/direction
- novelty
- importance
- confidence
- model_version

Candidate features per symbol and signal timestamp:
- article_count_{1h,6h,24h,72h}
- signed_sentiment_decay_{6h,24h,72h}
- novelty_weighted_sentiment
- importance_weighted_direction
- event-type one-hot/decay for earnings/guidance/M&A/legal/regulatory/product/management
- news breadth across the R5 universe
- cross-sectional rank of stock-specific news pressure

No article may affect a signal before available_at.

### E — Earnings expectations / revisions

This is specifically **analyst expectation revision**, not merely reported earnings surprise.

Required point-in-time history:
- symbol
- estimate period
- metric (EPS/revenue at minimum)
- estimate value
- analyst/consensus aggregation identifier
- effective_at / available_at
- revision direction and magnitude
- source/provider

Candidate features:
- 7d/30d consensus revision
- upward/downward revision breadth
- revision acceleration
- dispersion change
- days-to-earnings
- revision × price residual-momentum interaction

If point-in-time analyst revision history is unavailable, E remains DATA_BLOCKED. SEC filings or reported results must not be relabeled as analyst revisions.

## 4. R7.0 readiness gates

These are data-quality gates, not alpha gates.

### Macro M readiness
All required:
- >= 120 US high-impact release observations
- >= 24 months span
- >= 5 event families
- >= 95% usable point-in-time timestamps
- actual coverage >= 95%
- consensus coverage >= 80% for any surprise-based challenger
- event reaction data available for >= 80% of eligible releases if reaction features are used

If consensus coverage fails, only an explicitly labeled ACTUAL/REACTION-ONLY macro challenger may proceed.

### News N readiness
All required:
- >= 12 months point-in-time news history
- >= 80 of 93 R5 symbols mapped at least once
- on eligible trading timestamps, median symbol coverage >= 80 symbols
- exact/publisher/first-seen time quality >= 95%
- duplicate ratio <= 20%
- unmapped ratio <= 25%
- event/sentiment model version frozen before benchmark

### Earnings-revision E readiness
All required:
- >= 24 months history
- >= 70 of 93 R5 symbols
- >= 80% of earnings cycles contain at least two pre-event consensus snapshots
- effective_at / available_at explicit
- no backfilled latest-consensus substitution

## 5. R7.1 bounded challenger set

Only axes with READY status may enter.

Frozen maximum of four challengers:

- R7C0: frozen R5 relative-return HGB control
- R7C1: R5 + Macro M
- R7C2: R5 + News N
- R7C3: R5 + Earnings revisions E
- R7C4: R5 + equal-rank combination of independently READY information axes

No broad hyperparameter grid. HGB family and R5 execution stay fixed unless a separate pre-registered architecture version is created.

## 6. Evaluation

Use common decision timestamps and same execution:
- Top1
- R4 volatility sizing
- 10 bps
- exact +4 bucket non-overlap

Primary comparison:
- paired log-growth difference vs R5

Secondary:
- cumulative return
- PF
- MDD
- win rate
- fold stability
- concentration/effective names

Statistics:
- 5-trading-day moving-block bootstrap
- Holm adjustment across only the challengers actually admitted before execution

## 7. Survivor gate

All:
- >= 300 common trades
- primary log growth > R5
- PF >= R5
- MDD no worse than R5 by more than 2 percentage points
- positive paired folds >= 5
- paired bootstrap 95% lower CI > 0
- Holm p < 0.05
- effective names >= 5
- top ticker share <= 35%

No forced winner.

## 8. Governance

- R5.1 LIVE remains unchanged.
- R7.0 cannot change trading.
- Missing data is BLOCKED, not imputed from future information.
- A source may be historically revised only through vintage-aware data.
- News dedupe and first-seen timestamps are part of the model contract.
- Any provider change increments the data-contract version.
- R7 results may not reuse post-freeze prospective outcomes for redesign.

## 9. External-source notes

Official release schedules and values should prefer BLS/BEA/Federal Reserve primary sources. FRED/ALFRED is suitable for vintage-aware macro series and revision lineage, but FRED release dates are not automatically equivalent to point-in-time availability. Consensus expectations generally require an external point-in-time provider and must not be reverse-engineered from realized data.

## 10. Immediate action

Run `r7_point_in_time_readiness.py` against Neon.

Expected current state:
- M: BLOCKED — official news exists but structured release/surprise tables are empty
- N: BLOCKED — raw news exists, but stock-symbol historical breadth is insufficient
- E: BLOCKED — no point-in-time analyst-revision dataset

The next engineering work is ingestion/backfill, not model fitting.


## 11. R7-M historical backfill execution

Historical macro calendar ingestion reuses the existing production-normalization contract but is executed by a research-only runner:

- `research/r7_macro_backfill.py`
- `scripts/run_r7_macro_backfill.sh`

Default research window:
- start: 2020-01-01
- end: 2026-09-02
- market: US
- chunk size: 90 calendar days

Execution sequence is frozen:

1. `smoke` — one short historical window, no DB write.
2. `dry-run` — full history fetch + JSONL/manifest only, no DB write.
3. review per-indicator counts, consensus coverage and release-to-availability lag.
4. `write` — explicit upsert into `macro_release_observation` only after review.

Historical provider rows are tagged:

```
r7_backfill = true
r7_pit_audit = UNVERIFIED_PROVIDER_HISTORY
```

Therefore the existence of many backfilled rows alone cannot make R7-M READY.

Before R7-M readiness may pass, at least 95% of eligible macro rows must have:

- event-time availability within 120 minutes of the scheduled release; and
- `r7_pit_audit = PASS`.

This prevents historical backfill or revised provider values from being treated as verified point-in-time information merely because they exist in the database.


## 12. Free no-key macro path

The default R7-M research path no longer requires Trading Economics or any paid consensus provider.

Free sources:
- BLS Public Data API v1 (no registration key)
- BLS official release calendar
- Federal Reserve FOMC calendar / statement timing

Initial free families:
- CPI / Core CPI
- Employment Situation: NFP, unemployment rate, AHE
- PPI
- JOLTS
- FOMC

Governance:
- consensus is unavailable and is never fabricated.
- BLS API historical series are tagged `REVISED_SERIES_NOT_PIT`; they may contain later revisions and are not treated as first-release vintages.
- official archived BLS news releases are parsed separately as first-release PIT candidates.
- BLS pages marked reissued/corrected remain event-level missing rather than being backfilled from revised history.
- the preregistered actual-coverage gate remains the original overall >=95% rule; per-family coverage is diagnostic and is not retroactively promoted into a new gate after observing results.
- explicit DB write remains blocked in the free runner until the reaction layer is validated.

Default runner:
`scripts/run_r7_macro_backfill.sh smoke` -> free smoke
`scripts/run_r7_macro_backfill.sh full` -> free 2020-2026 collection
`write` -> blocked


### 2020-2026 free actual-layer audit (2026-09-22)

Observed on `kalman-r7-macro-free-v4`:
- 367 total events across CPI, Employment, FOMC, JOLTS, PPI.
- 320 BLS archive attempts; 320 fetched; 320 parsed.
- 311 PIT-eligible archived releases.
- overall PIT archive coverage = 97.1875%.
- CPI = 100%, PPI = 100%, JOLTS = 100%.
- Employment = 88.75% because 9 official BLS pages are marked reissued/corrected and remain conservatively unavailable.
- FOMC is event-time only and is outside the BLS archive denominator.

Decision:
- `pit_actual_ready = true` under the preregistered overall >=95% actual coverage gate.
- no retroactive family-level 95% gate is introduced after observing results.
- event-level availability masks must exclude the 9 Employment reissue/correction rows from any R7 feature.
- R7-M remains blocked because `reaction_ready = false`; consensus is also unavailable for surprise-based challengers.


## 13. Free session-reaction contract

The free reaction path is explicitly labeled `QQQ_SESSION_REACTION_1H`. It is not an intraday US2Y yield reaction and must never be described as one.

Source:
- canonical `QQQ_1h_gap_aware.parquet`
- canonical-history contract: 60m bars derived from complete 15m constituents, six full regular-session buckets, final regular 30m tail excluded, no forward-filled gaps.

PIT alignment:
- choose the first complete 60m QQQ bar whose `candle_time_utc >= release_at`.
- a bar that straddles the release is never used.
- require the first post-event full bar to begin within 6 hours of the event.
- `reaction_available_at = first_full_bar_start + 60 minutes`.
- the feature cannot enter any model timestamp before `reaction_available_at`.
- 2h reaction requires `expected_seq + 1` and the same `session_date`; it may not bridge overnight.
- BLS rows marked reissued/corrected remain event-input ineligible.
- FOMC statement timestamps are event-input eligible even without a BLS actual value.

Primary reaction field:
- QQQ first-full-bar open-to-close return.

Secondary diagnostics:
- previous-close to first-full-bar close return.
- same-session 2h open-to-close return when available.
- anchor delay in minutes.

Readiness:
- session reaction coverage >=80% over event-input-eligible releases that fall within canonical QQQ history.
- per-family reaction coverage is reported diagnostically.
- even if this gate passes, it only admits an explicitly named ACTUAL/SESSION_REACTION-ONLY challenger. It does not authorize consensus-surprise features or claim intraday US2Y repricing.


## 14. R7.1 bounded macro challenger

Exactly one free-data macro challenger is admitted after R7.0 readiness:

`R7C1_ACTUAL_SESSION_REACTION_ONLY`

Unchanged from R5:
- HGB model family / cloned estimator parameters
- target: `relative_ret_4b = stock fwd_ret_4b - same-timestamp universe median fwd_ret_4b`
- R5 20-feature base set
- Top1 execution
- R4 volatility sizing
- 10 bps cost
- exact +4 expected-seq non-overlap
- E2-E8 paired common-OOS evaluation
- 5-trading-day moving-block bootstrap, B=2000

Added macro features, fixed before performance inspection:
- `m_event_decay_24h`
- `m_actual_delta_pressure_decay`
- `m_session_reaction_1h_decay`
- family-specific decays for CPI / Employment / PPI / JOLTS / FOMC

Macro state contract:
- latest reaction-available macro event only
- event half-life = 24h
- hard max age = 72h
- actual component = change from prior PIT-eligible first-release actual, not consensus surprise
- fixed unit scales/policy signs: CPI 0.1, Core CPI 0.1, NFP 50 thousand, unemployment 0.1 with negative policy sign, AHE 0.1, PPI 0.2, JOLTS 250 thousand
- component z-values clipped to +/-5 then averaged within event
- session reaction = QQQ first complete post-event 60m open-to-close return
- no consensus
- no intraday US2Y claim

Critical timing:
- canonical R5 row `timestamp` is the 60m bar start.
- model decision information cutoff is `signal_as_of = timestamp + 60 minutes`.
- a macro event enters R7C1 only when its `reaction_available_at <= signal_as_of`.
- the 2h reaction remains diagnostic and has its own later availability timestamp; it is not an R7C1 feature.

Preflight fail-closed checks:
- R7 actual readiness must pass.
- R7 session-reaction readiness must pass.
- frozen 497,504 scored-row count and 93-symbol universe must match.
- base R5 features must reconcile to frozen scored rows.
- reconstructed `relative_ret_4b` must reconcile to frozen target.
- all frozen fold training counts must match.
- challenger non-overlap schedule must exactly match frozen R5 baseline schedule.

Survivor gate remains the frozen R7 gate:
- >=300 common trades
- log growth > R5
- PF >= R5
- MDD no worse than R5 by more than 2 percentage points
- >=5 positive paired folds
- paired bootstrap 95% lower CI > 0
- one-challenger Holm p < .05
- effective names >=5
- top ticker share <=35%

No forced winner. R5.1 LIVE remains untouched.
