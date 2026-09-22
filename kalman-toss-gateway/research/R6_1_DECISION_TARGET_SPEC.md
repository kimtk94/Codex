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

R6.1 v4 separates training and evaluation sources.

**Challenger training source**
- frozen `r1_directional_v1_2/primary_train/{SYMBOL}_r1.parquet`
- restricted to the same frozen 93 R5 symbols
- R5.0.1 uses its broader **all-valid-target-row** eligibility, not the older R1 `feature_core_valid=True` mask
- missing predictor values are median-imputed exactly as documented by the frozen R5 training-median artifact
- the R5 cross-sectional feature family is reconstructed from those frozen R1 rows
- reconstructed features must reconcile against frozen R5 scored rows with:
  - >5,000 matched rows
  - median absolute numeric difference <=1e-10
  - finite-state agreement >=99.9%

**Evaluation / control source**
- `r5_0_1_scored_rows.parquet` — authoritative OOS feature rows
- `r5_0_1_trade_ledger.parquet` — authoritative R5C0 baseline trades
- prior R6 `R5_BASE_4H` — authoritative E2-E8 common-OOS metric scope
- `model_freeze/r5_hgb.joblib` — HGB estimator template

Path-dependent labels do not infer +1..+4 bars from scored-row adjacency. They read exact expected-sequence OHLC from `canonical_history_v1` plus the pre-cutoff `r4_live_canonical_v1` overlay.

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

Path labels require complete +1/+2/+3/+4 OHLC coverage from canonical OHLC. The primary 4H endpoint label remains valid even when an intermediate bar is genuinely absent, so path-dependent labels are trained/evaluated only where the full path is observed. Required path coverage is >=95%, and coverage is reported explicitly.

## Walk-forward folds

The frozen `r5_0_1_scored_rows.parquet` contains 497,504 OOS rows. The separate 831,981 count belongs to the final R5.1 all-data freeze fit.

R6.1 v4 reconstructs the original expanding training history from frozen R1 rows and enforces the exact R5.0.1 fold counts:

- E1 train = 333,560
- E2 train = 402,199
- E3 train = 469,975
- E4 train = 536,765
- E5 train = 604,724
- E6 train = 670,525
- E7 train = 739,716
- E8 train = 784,713

E2-E8 are used for the paired common-OOS R6.1 comparison so the baseline remains identical to the prior R6 `R5_BASE_4H` scope.

For every evaluated fold:

`train.target_timestamp_4b < fold_start`

Any training-row mismatch aborts the run. The preflight also requires the final R5.1 freeze contract exactly: 831,981 rows, first feature timestamp 2020-07-27 13:30 UTC, last feature timestamp 2026-09-01 14:30 UTC, and last target timestamp 2026-09-01 18:30 UTC.

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
- proxy coverage >=95%
- >=5/8 positive paired folds
- paired bootstrap 95% lower CI >0
- Holm-adjusted one-sided p <0.05
- trades >=300
- effective names >=5
- top ticker share <=35%

No forced winner. Passing is research evidence only; LIVE R5.1 remains unchanged until separately reviewed.
