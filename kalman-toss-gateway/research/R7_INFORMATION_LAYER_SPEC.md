# Kalman R7 — Point-in-Time Information Layer

**Status:** PRE-REGISTERED / RESEARCH ONLY  
**Date:** 2026-09-22  
**Production:** unchanged  
**Champion:** R5.1 `R5C0_HGB_REFERENCE`

## 1. Why R7 exists

R6 and R6.1 tested post-filtering, selective prediction, adaptive horizon, and alternative target definitions. None produced a research survivor versus the frozen R5 baseline.

R7 therefore does **not** tune the R5 score, target, threshold, risk rule, or exit horizon again.

The only permitted research question is:

> Does genuinely new point-in-time information add incremental cross-sectional alpha to the frozen R5 feature family?

The three information families are:

1. macro release surprise + rate/policy repricing;
2. timestamped company/news information;
3. point-in-time earnings-estimate revisions.

## 2. Non-negotiable control

R7 uses the same control/evaluation mechanics as the validated R5/R6 comparison:

- frozen 93-symbol universe;
- frozen R5 20-feature family;
- Histogram Gradient Boosting family;
- Top1;
- R4 volatility sizing;
- 10 bps cost;
- exact +4 expected-sequence exit;
- exact non-overlap;
- E2-E8 paired common-OOS schedule;
- frozen R5 trade ledger as the control.

No R7 result may modify LIVE or Production directly.

## 3. Stage R7.0 — Information readiness gate

R7.0 is a **data-contract stage**, not a model tournament.

A data family cannot enter model fitting until all point-in-time requirements pass.

### 3.1 Macro surprise

Required record semantics:

- `release_at`: actual scheduled/reported event time;
- `available_at`: earliest timestamp at which the value could have been known by the strategy;
- `actual`;
- `consensus`;
- `previous`;
- stable indicator key;
- source/provenance;
- timestamp-quality flag.

Priority US event families:

- CPI / Core CPI;
- Core PCE;
- NFP / unemployment / average hourly earnings;
- PPI;
- Retail Sales;
- ISM Manufacturing / Services;
- JOLTS;
- Initial Jobless Claims;
- FOMC decision / projections.

Primary surprise value is standardized only with **prior events** of the same indicator.

No final revised value may replace the value that was available at the decision timestamp.

### 3.2 Rate / policy repricing

The preferred event-reaction layer is intraday and event-anchored:

- US 2Y change around release;
- policy-proxy / Fed-pricing change around release;
- event timestamp known before joining to model rows.

Daily DGS2/DFF levels may be retained as diagnostics but are **not sufficient** to promote an event-reaction candidate.

### 3.3 News

Official release/news records may support macro-event timestamping.

A standalone **company-news** R7 candidate requires symbol-level PIT coverage. Global-only news snapshots are insufficient for a 93-stock cross-sectional selector.

Required:

- `available_at <= model decision time`;
- timestamp provenance;
- deduplication;
- ticker/entity attribution;
- stable feature version;
- historical coverage across the research window.

### 3.4 Earnings revisions

Current analyst estimates are not historical PIT estimates.

An earnings-revision source is eligible only if it preserves the estimate/consensus as it existed at the historical `available_at` timestamp.

Required stock-level fields include, at minimum:

- symbol;
- estimate period;
- metric (EPS/revenue);
- estimate value;
- observation/available timestamp;
- prior estimate or enough PIT observations to calculate revisions;
- analyst-count/support when available.

## 4. R7.0 readiness gates

### Macro consensus-surprise gate

All required:

- >= 150 mapped US priority releases;
- >= 90% with non-null consensus;
- >= 95% with non-null actual;
- >= 90% with acceptable release-time quality;
- zero `available_at < release_at` violations;
- >= 24 months of usable history.

### Macro repricing gate

All required:

- event-linked reaction/repricing observations >= 150;
- >= 85% coverage of macro-surprise events;
- exact/provider timestamp semantics;
- no use of future close or end-of-day value for an intraday decision.

### Company-news gate

All required:

- `market='US'` symbol-level snapshots;
- >= 80 distinct R5 symbols;
- >= 12 months history;
- >= 5,000 symbol/timestamp snapshots;
- mean coverage confidence >= 0.70;
- no timestamp lookahead violation.

### Earnings-revision gate

Blocked until a PIT source/table exists and its timestamp contract is audited.

## 5. Candidate family — only after readiness

R7.1 permits **three individual challengers only**:

- `R7C0_R5_CONTROL` — frozen R5 feature/control behavior;
- `R7C1_MACRO_EVENT_HGB` — R5 features + macro surprise/repricing;
- `R7C2_COMPANY_NEWS_HGB` — R5 features + company-news features;
- `R7C3_EARNINGS_REV_HGB` — R5 features + PIT earnings revisions.

A challenger whose source does not pass R7.0 is **BLOCKED**, not imputed as neutral and not replaced with a proxy.

No combined macro+news+earnings model is allowed in R7.1. A combined model may be pre-registered later only if at least two independent information families survive R7.1.

## 6. PIT join rule

For a model decision timestamp `t`:

```text
feature.available_at <= t
```

is mandatory.

When multiple observations exist, use the latest observation known at `t`.

No backward assignment from a later observation is permitted.

## 7. Evaluation

For every runnable challenger:

- same E2-E8 paired common-OOS timestamps as R5;
- same HGB estimator family;
- same training boundaries;
- same Top1 / sizing / cost / exit rules;
- exact schedule audit;
- 5-trading-day moving-block paired bootstrap;
- Holm adjustment across the **runnable** R7.1 challengers;
- fold stability;
- MDD / PF / concentration diagnostics.

## 8. Survivor rule

A challenger must simultaneously satisfy:

- exact schedule parity;
- trades >= 300;
- primary log growth > R5 control;
- profit factor >= R5 control;
- MDD no worse than control by more than 2 percentage points;
- >= 5 positive paired folds;
- paired bootstrap 95% lower bound > 0;
- Holm-adjusted p < 0.05;
- effective names >= 5;
- top ticker share <= 35%.

No forced winner.

## 9. Current source strategy

### Macro actual/vintage

Official/FRED/ALFRED data are acceptable for historical actual/vintage reconstruction when the release/availability contract is explicit.

### Consensus

Consensus requires a provider with historical PIT calendar snapshots. A provider that exposes only today's consensus must not be backfilled.

### News

Existing Kalman news tables can be audited immediately, but current R7 eligibility depends on historical **US symbol-level** coverage rather than merely having a news corpus.

### Earnings

A vendor endpoint that exposes current analyst estimates is insufficient by itself. Historical revision/PIT semantics must be demonstrated before use.

## 10. Production invariant

R7 is research-only.

```text
R5.1 LIVE/Production = unchanged
R7 trade execution   = disabled
R7 auto promotion    = forbidden
```
