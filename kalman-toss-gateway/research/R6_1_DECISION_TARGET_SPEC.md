# Kalman R6.1 — Decision-Aware Target Ablation

**Date:** 2026-09-22  
**Status:** research-only / final R6 attempt  
**Production:** unchanged  
**Research cutoff:** `2026-09-02T13:30:00Z`

## Purpose

R6 v1 showed that a post-R5 selective/meta classifier did not add stable edge. R6.1 therefore tests a narrower hypothesis:

> Keep the proven R5 HGB architecture, frozen feature rows, risk sizing, 4H horizon, and execution policy; change only the supervised target.

No post-cutoff R5.1 prospective outcome is used for model selection.

## Authoritative source contract

R6.1 does **not** rebuild R5 features from raw canonical data.

It uses the frozen R5.0.1 artifacts directly:

- `r5_0_1_scored_rows.parquet` — authoritative feature/target rows
- `r5_0_1_trade_ledger.parquet` — authoritative R5C0 baseline trades
- `r5_0_1_leaderboard.csv` — authoritative baseline metrics
- `model_freeze/r5_hgb.joblib` — authoritative HGB estimator template

The frozen scored rows contain the original OHLC, exact expected-sequence semantics, 20 R5 features, `relative_ret_4b`, and `R5C0_HGB_REFERENCE`.

## Control

### R6T0_RELATIVE_HGB

The control is **not retrained**.

R6T0 is the frozen `R5C0_HGB_REFERENCE` trade ledger itself. Before any challenger is interpreted, the frozen ledger must reproduce the frozen leaderboard on:

- trade count
- 10bp cumulative return
- log growth
- MDD

Tolerance: `1e-10`.

This prevents feature reconstruction or preprocessing drift from creating a false R6 improvement.

## Challengers

All challengers clone the frozen `r5_hgb.joblib` estimator and use the same frozen 20-feature family.

### R6T1_NET_HGB

`target_net = weight * fwd_ret_4b - weight * 0.001`

where

`weight = clip(universe_median_rv24 / rv24, 0.25, 1.00)`

This aligns the target with the actual volatility-targeted, cost-aware 4H execution objective.

### R6T2_ORDINAL_NET_HGB

Within each timestamp:

`target = percentile_rank(target_net) - 0.5`

This tests whether a continuous ordinal transformation improves Top1 selection while keeping HGB unchanged.

### R6T3_PATH_REL_HGB

Using the frozen scored-row OHLC and exact expected sequence, reconstruct the first four future 1H bars:

- stop = -3%
- take profit = +20%
- max hold = 4 buckets
- same-bar stop/TP ambiguity = stop first
- otherwise exit at +4 close

Then:

`proxy_net = weight * proxy_return - weight * 0.001`

`target = proxy_net - same_timestamp_median(proxy_net)`

Path labels require complete +1/+2/+3/+4 OHLC coverage. Overall and selected-trade proxy coverage must be at least 99%.

## Walk-forward folds

Same R5 research folds:

- E1 2023H1
- E2 2023H2
- E3 2024H1
- E4 2024H2
- E5 2025H1
- E6 2025H2
- E7 2026 Jan-Apr
- E8 2026 May to cutoff

For each fold:

`train.target_timestamp_4b < fold_start`

The test set is the frozen R5 scored rows inside the fold.

## Execution

For all challengers:

- Top1
- volatility target `clip(universe_median_rv24 / rv24, 0.25, 1.00)`
- 10bp round-trip approximation
- exact +4 expected-sequence non-overlap

Each challenger must produce exactly the same decision timestamps as the frozen R5 baseline. A schedule mismatch aborts the run.

## Evaluation

Primary metric:

`weight * fwd_ret_4b - weight * 0.001`

Secondary operational proxy:

`weight * path_proxy_ret - weight * 0.001`

Statistics:

- paired daily log-return differences vs frozen R5C0
- 5-trading-day moving-block bootstrap, B=2000
- Holm correction across exactly 3 challengers
- fold stability
- PF / MDD
- concentration / effective names

## Survivor gate

A challenger survives only if all hold:

- primary log growth > frozen R5C0
- primary PF >= frozen R5C0
- primary MDD no worse by >2 percentage points
- production-proxy log growth >= frozen R5C0
- proxy coverage >=99%
- >=5/8 positive paired folds
- paired bootstrap 95% lower CI >0
- Holm-adjusted one-sided p <0.05
- trades >=300
- effective names >=5
- top ticker share <=35%

No forced winner. Passing is research evidence only; LIVE R5.1 remains unchanged until separately reviewed.
