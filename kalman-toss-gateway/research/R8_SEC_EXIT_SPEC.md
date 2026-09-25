# Kalman R8 — SEC Corporate Events + Prospective Exit Shadow

**Pre-registered:** 2026-09-22
**Mode:** RESEARCH_ONLY
**Production/LIVE:** unchanged
**Champion:** R5.1_BASE_HGB

## 1. Purpose

R6/R6.1 and R7-M did not beat frozen R5.1. R8 therefore does not retune R5.1, R7-M decay, thresholds, targets, or risk rules.

R8 opens two independent research tracks:

1. **R8-S SEC Corporate Event Layer** — symbol-specific, point-in-time corporate events from SEC EDGAR.
2. **R5-EXIT-V1 Prospective Multi-Horizon Shadow** — keep the current R5.1 Top1 selector fixed and prospectively observe 2h/4h/6h/8h outcomes.

The two tracks must not be combined until each has its own clean evidence.

## 2. R8-S SEC event source contract

Primary sources:
- SEC `data.sec.gov/submissions/CIK##########.json`
- historical submission files listed in `filings.files`
- SEC company ticker/CIK mapping

No API key is used.

Fair-access contract:
- explicit User-Agent
- request rate capped below SEC's published 10 requests/second limit
- no broad archive crawling
- only the frozen R5 93-symbol universe is queried

PIT timestamp:
- `acceptanceDateTime`
- no filing can affect a signal before `acceptanceDateTime <= signal_as_of`

Important limitation:
- SEC documents the EDGAR acceptance timestamp but does not provide a separate timestamp proving the exact instant a filing became publicly retrievable on sec.gov.
- R8-S therefore labels this timestamp quality `EDGAR_ACCEPTANCE_TIME`, not `PUBLIC_FIRST_SEEN_EXACT`.

## 3. R8-S initial event families

Only 8-K / 8-K/A are collected in v1.

Frozen item buckets:

- `EARNINGS_RESULTS`: 2.02
- `MATERIAL_AGREEMENT`: 1.01
- `ACQUISITION_DISPOSITION`: 2.01
- `FINANCING_OBLIGATION`: 2.03, 3.02
- `DELISTING_COMPLIANCE`: 3.01
- `RESTRUCTURING_IMPAIRMENT`: 2.05, 2.06
- `MANAGEMENT_BOARD`: 5.02
- `REG_FD`: 7.01
- `OTHER_EVENT`: 8.01
- `FINANCIAL_EXHIBITS`: 9.01

No sentiment or direction is inferred in readiness v1.

## 4. R8-S readiness gate

Data-quality only. No alpha fitting before all required gates pass.

- frozen universe loaded successfully
- >= 90 / 93 symbols mapped to SEC CIK
- >= 24 months event span
- >= 70 / 93 symbols with at least one 8-K/8-K/A
- >= 500 PIT event rows
- >= 95% non-null acceptance timestamps
- accession duplicate ratio <= 1%
- >= 80% event rows contain at least one semantic item bucket other than stand-alone 9.01 Financial Statements/Exhibits

If the item-coverage gate fails, an event-presence-only challenger may later be separately preregistered; the gate is not relaxed post-result.

## 5. Future R8C1 rule

R8C1 is NOT admitted by this spec.

If R8-S passes readiness, a new pre-registered ablation may test a single bounded SEC-event challenger.

R5 execution stays frozen:
- Top1
- R4 volatility sizing
- 10 bps
- exact +4 expected-seq
- common paired schedule

No model fitting is performed by the SEC backfill/readiness scripts.

## 6. R5-EXIT-V1 prospective contract

Purpose: observe whether the already-frozen R5.1 selector has a better holding horizon without using historical post-hoc horizon selection.

Prospective boundary:

`2026-09-22T10:45:00Z`

Only R5.1 strategy signals whose decision timestamp is at or after this boundary are eligible.

Selector:
- `R5.1_BASE_HGB`
- Top1 signal unchanged
- no refit
- no signal filtering
- no macro/news/SEC inputs

Frozen horizons recorded simultaneously:
- 2 complete canonical 60m buckets
- 4 complete canonical 60m buckets
- 6 complete canonical 60m buckets
- 8 complete canonical 60m buckets

Reference:
- entry price = canonical close of the signal bucket
- horizon price = canonical close at exact `expected_seq + horizon`
- no row-shift horizon approximation
- no missing-bar bridging
- no forward fill

Primary stored outcomes:
- gross return
- R4-weighted 10 bps net return
- horizon maturity timestamp

This is an observational prospective ledger. It does not change LIVE exits.

## 7. Exit-shadow governance

Every unique `symbol + as_of` signal gets a deterministic signal_id.

Signal rows are immutable once written.

Outcome rows are appended only after the exact horizon is mature.

Existing signal/outcome values cannot be overwritten with different values.

Before any horizon recommendation:
- >= 100 mature outcomes per horizon
- >= 60 distinct signal trading days

Preferred review:
- >= 150 mature outcomes per horizon
- >= 90 distinct days

A future decision rule must be pre-registered before comparing horizons for promotion.

## 8. Production invariant

R8-S and R5-EXIT-V1:
- do not submit orders
- do not change R5.1 model
- do not change current 4-bucket LIVE max-hold
- do not alter risk sizing
- do not write strategy signals
- do not alter production tables



## 9. SEC issuer-lineage correction before alpha fitting

The first readiness run exposed one clear historical-lineage discontinuity:
- current XOM ticker mapping points to successor registrant CIK `0002115436`, yielding only three 2026 events;
- SEC identifies ExxonMobil Holdings Corporation as successor registrant effective 2026-07-01;
- predecessor Exxon Mobil Corporation used CIK `0000034088`.

R8-S v2 therefore freezes:
- XOM / CIK 0000034088 through 2026-06-30
- XOM / CIK 0002115436 from 2026-07-01 onward

This correction is source-lineage repair before any alpha model is fit; it is not performance-driven tuning.

Duplicate governance is also clarified:
- uniqueness key = `symbol + accession_number`;
- the same SEC accession may intentionally map to multiple traded share classes of the same issuer (for example GOOG/GOOGL);
- cross-symbol shared accessions are reported diagnostically and do not count as within-symbol duplicates.


## 10. R8.1 bounded SEC challenger — preregistered before performance inspection

Readiness input frozen at SEC v2:
- 93/93 mapped symbols
- 93/93 symbols with events
- 8,858 8-K / 8-K/A rows
- 100% acceptance timestamp coverage
- 89.2301% semantic-item coverage excluding stand-alone 9.01-only rows
- 0% within-symbol accession duplicates
- XOM predecessor/successor CIK lineage repaired before alpha fitting

Exactly one challenger is admitted:

`R8C1_SEC_CORPORATE_EVENT`

No alternate SEC feature subset, decay, or item weighting is evaluated inside R8.1.

Unchanged from frozen R5:
- cloned HGB estimator family / parameters
- 20 R5 base features
- target = `relative_ret_4b`
- Top1 execution
- R4 volatility sizing
- 10 bps cost
- exact +4 expected-seq non-overlap
- E2-E8 paired common-OOS schedule
- 5-trading-day moving-block bootstrap, B=2000

Added SEC features:
- `sec_any_decay_48h`
- `sec_event_count_120h_log1p`
- `sec_earnings_results_decay_48h`
- `sec_material_agreement_decay_48h`
- `sec_acquisition_disposition_decay_48h`
- `sec_financing_obligation_decay_48h`
- `sec_restructuring_impairment_decay_48h`
- `sec_management_board_decay_48h`
- `sec_reg_fd_decay_48h`
- `sec_other_event_decay_48h`
- `sec_delisting_compliance_decay_48h`

Frozen SEC feature contract:
- event timestamp = EDGAR `acceptanceDateTime`
- conservative publication availability = `acceptanceDateTime + 5 minutes`
- `signal_as_of = R5 timestamp + 60 minutes`
- only events with `acceptanceDateTime + 5 minutes <= signal_as_of` may enter
- half-life = 48 calendar hours
- hard max age = 120 calendar hours
- bucket feature = decay of latest event containing that semantic bucket
- event-count feature = `log1p(number of semantic 8-K filings in prior 120 calendar hours)`
- stand-alone 9.01 Financial Statements/Exhibits is not a semantic event
- no filing text
- no sentiment
- no directional hand-label
- no SEC event return/reaction feature
- no post-result feature selection

Fail-closed preflight:
- SEC manifest schema must be `kalman-r8-sec-corporate-events-v2`
- `sec_event_ready=true`
- frozen 93-symbol universe
- frozen 497,504 scored rows
- R5 base-feature reconciliation
- frozen `relative_ret_4b` target reconciliation
- frozen fold training-row counts
- challenger non-overlap schedule exact-match to R5

Frozen survivor gate:
- >=300 common trades
- log growth > R5
- PF >= R5
- MDD no worse than R5 by more than 2 percentage points
- >=5 positive paired folds
- paired moving-block bootstrap 95% lower CI > 0
- one-challenger Holm p < .05
- effective names >=5
- top ticker share <=35%

No forced winner. Regardless of result, `live_action=NONE` until a separate promotion decision.

## 11. R5-EXIT-V1 automatic collection

Prospective exit-shadow is scheduled once per US trading day after the session:
- Tue-Sat 08:15 KST
- after the existing 07:45 SHADOW portfolio ranking
- read-only strategy_signal input
- exact canonical `expected_seq + 2/+4/+6/+8` outcomes
- append-only immutable research ledger

The scheduled collector does not invoke Toss, auto-trade, position manager, or any LIVE exit path.


## 12. R8.1 observed result — rejected for alpha promotion

Observed after all preregistered integrity gates passed:

R5:
- cumulative return +116.9751%
- log growth 0.774612
- PF 1.207053
- MDD -22.6589%

R8C1:
- cumulative return +111.9022%
- log growth 0.750955
- PF 1.203229
- MDD -17.4001%
- win rate 51.6295%
- median trade return 0.03035%
- effective names 35.7904
- top ticker share 6.8121%

Paired:
- mean daily log diff -0.0000302917
- 95% CI [-0.000814595, +0.000785083]
- p / Holm = 0.517241
- positive paired folds = 4/7

Decision:
- `research_survivor=false`
- `promotion_eligible=false`
- `live_action=NONE`
- R5.1 remains champion.

Interpretation:
- SEC event data are technically usable and symbol-specific;
- the fixed SEC feature encoding does not add statistically supported alpha over R5;
- drawdown and diversification improved materially, so SEC may be studied as a future risk tag/overlay only under a new prospective preregistration;
- no retrospective R8.1 threshold/decay/item-subset tuning is permitted.


## 13. R8-RISK-V1 prospective passive SEC tag — preregistered before first signal

At the time of this preregistration, `R5-EXIT-V1` contains:
- signal rows = 0
- outcome rows = 0

Therefore passive SEC context can be frozen before any prospective outcome is observed.

For every future R5.1 exit-shadow signal, record without changing the trade:
- `sec_active_120h`
- `sec_any_decay_48h`
- `sec_event_count_120h`
- `sec_latest_buckets_csv`
- `sec_latest_event_available_at`

Contract:
- semantic SEC buckets only; stand-alone 9.01-only filing does not activate the tag
- availability = EDGAR acceptanceDateTime + 5-minute embargo
- SEC-active = at least one semantic event in prior 120 calendar hours
- latest-event decay half-life = 48 calendar hours
- passive metadata only
- no size change
- no signal filtering
- no exit change
- no order suppression

The historical R8.1 MDD improvement is only motivation for prospective observation and is not a promotion rule.

No SEC risk overlay may be recommended until a separate prospective review rule is preregistered and the minimum sample is reached.

Minimum descriptive review:
- >= 40 SEC-active mature 4h outcomes
- >= 100 total mature 4h outcomes
- >= 60 distinct prospective signal days

Until then, SEC tags are stored only and no risk decision is made.
