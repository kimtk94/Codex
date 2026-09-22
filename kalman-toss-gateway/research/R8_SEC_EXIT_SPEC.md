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
- >= 80% event rows contain at least one recognized item bucket

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

