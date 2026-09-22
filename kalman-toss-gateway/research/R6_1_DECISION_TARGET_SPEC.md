# Kalman R6.1 — Decision-Aware Target Ablation

**Date:** 2026-09-22  
**Status:** research-only / pre-registered final R6 attempt  
**Production:** unchanged  
**Research cutoff:** `2026-09-02T13:30:00Z`

## Question

Can the proven R5 HGB selector improve when its **training target** is aligned more closely with the long-only, volatility-targeted, cost-aware execution objective, without changing the model class, feature family, risk sizing, horizon, or execution policy?

The failed R6 v1 selective/meta layer is retained as negative evidence. R6.1 does not use a second classifier and does not use post-2026-09-02 R5.1 prospective outcomes for model selection.

## Frozen data and model contract

- 93-symbol R5 research universe.
- locked `canonical_history_v1` + pre-cutoff `r4_live_canonical_v1` overlay.
- exact expected-sequence gap semantics.
- same 20-feature R5 HGB family.
- same HGB hyperparameters:
  - learning_rate = 0.05
  - max_iter = 100
  - max_leaf_nodes = 15
  - min_samples_leaf = 100
  - l2_regularization = 1.0
  - random_state = 42
- Top1.
- R4 volatility target: `clip(universe_median_rv24 / rv24, 0.25, 1.00)`.
- 10 bps round-trip cost approximation.
- exact +4 bucket non-overlap.

Only the target changes.

## Candidates

### R6T0_RELATIVE_HGB — frozen control

`fwd_ret_4b - same_timestamp_median(fwd_ret_4b)`

This must reconcile to the existing R5C0 HGB reference before any challenger is interpreted.

### R6T1_NET_HGB — cost-aware absolute target

`weight * fwd_ret_4b - weight * 0.001`

The weight is known at decision time and is the same volatility target used by execution.

### R6T2_ORDINAL_NET_HGB — continuous ordinal utility target

Within each timestamp, percentile-rank the R6T1 realized net return and center it:

`rank_pct(net_return) - 0.5`

This changes the target transformation while keeping HGB unchanged. It is distinct from the failed CatBoost/XGBoost pairwise ranker candidates in R5.0.

### R6T3_PATH_REL_HGB — execution-path relative utility

Build a conservative 4-bucket production proxy using the frozen live exit semantics:

- stop = -3%
- take profit = +20%
- maximum hold = 4 buckets
- if stop and TP are both touched inside the same 1H bar, count stop first
- otherwise time-exit at bucket +4 close

Then:

`proxy_net = weight * proxy_return - weight * 0.001`

`target = proxy_net - same_timestamp_median(proxy_net)`

This preserves R5's cross-sectional relative-target idea while aligning the realized target with the operational stop/time-exit path.

## Walk-forward folds

Same eight R5 research folds:

- E1 2023H1
- E2 2023H2
- E3 2024H1
- E4 2024H2
- E5 2025H1
- E6 2025H2
- E7 2026 Jan-Apr
- E8 2026 May to 2026-09-02 cutoff

For every fold:

`train.target_timestamp_4b < test_start`

and test rows remain inside the fold boundary. No post-cutoff rows are eligible.

## Evaluation

Primary continuity metric:

`weighted 4H close return - 10 bps * weight`

Secondary operational metric:

`weighted production-proxy return - 10 bps * weight`

All candidates are executed with the same Top1 + exact 4-bucket non-overlap policy.

Statistics:

- paired daily log-return differences versus R6T0
- 5-day moving-block bootstrap, B=2000
- Holm correction across the three challengers
- fold stability
- profit factor
- max drawdown
- concentration / effective names

## Mandatory baseline reconciliation

R6T0 must reproduce the frozen R5C0 reference from `r5_0_1_leaderboard.csv` on:

- trade count
- 10 bps cumulative return
- log growth
- MDD

Tolerance for floating metrics: `1e-8`.

If this fails, R6.1 stops and no challenger result is valid.

## Research survivor gate

A challenger is a research survivor only if all are true:

- primary 4H log growth > R6T0
- primary profit factor >= R6T0
- primary MDD is no worse than R6T0 by more than 2 percentage points
- production-proxy log growth >= R6T0
- positive paired folds >= 5 / 8
- paired bootstrap 95% lower CI > 0
- Holm-adjusted one-sided p < 0.05
- trades >= 300
- effective names >= 5
- top ticker share <= 35%

No forced winner.

## Selection

If multiple challengers survive:

1. highest primary log growth
2. lower absolute MDD
3. higher production-proxy log growth
4. higher effective names
5. lexicographic candidate ID

Passing this gate is **research evidence only**. It does not alter LIVE R5.1.

## External rationale

- Cakici & Zaremba (2026), *Getting the Target Right in Return Prediction*, reports that target-return transformation can materially change ML return-prediction and portfolio performance.
- *Machine Learning and the Implementable Efficient Frontier* (Review of Financial Studies, 2026) argues for aligning ML portfolio decisions with net-of-trading-cost economic objectives.

R6.1 uses those ideas only as motivation; acceptance depends entirely on Kalman's frozen walk-forward evidence.
