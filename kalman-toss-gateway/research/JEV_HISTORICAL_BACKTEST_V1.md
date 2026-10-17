# JEV Historical Blind Replay V1

Generated: 2026-10-07

## Decision

**Do not promote JEV to live veto/sizing based on the current historical evidence.**

The pre-specified leakage-safe variants do not improve the R5.1 baseline. A very strong result observed in broader MARKET/UNIVERSE variants was traced to future-label leakage in three columns and is invalid.

JEV remains research/shadow only.

## Baseline contract

- Strategy: R5.1 / R5C0_HGB_REFERENCE
- Historical evaluation range: 2023-01-03 through 2026-08-31
- Opportunities: 1,340 non-overlapping FIXED_4 admissions
- Cost: 10 bps
- Friday-flat: already reflected in actual trade returns; 176 admissions affected
- Candidate identity sent to JEV: blinded
- Absolute date sent to JEV: blinded
- Future outcome sent to JEV: never
- Outcome: TOP1 actual net return from r5_topk_portfolio_trade_detail.parquet

### R5.1 score OOS contract

The score panel is generated using eight temporal walk-forward folds. In every fold, train_last_target is earlier than test_first:

- E1 2023H1
- E2 2023H2
- E3 2024H1
- E4 2024H2
- E5 2025H1
- E6 2025H2
- E7 2026 Jan-Apr
- E8 2026 May-cutoff

The selected primary is R5C0_HGB_REFERENCE.

## Primary results

| Variant | Arm | Coverage | Total return | CAGR | MDD | Opportunity Sharpe | Result |
|---|---|---:|---:|---:|---:|---:|---|
| Baseline | R5.1 | 100.0% | +311.98% | 47.27% | 36.13% | 1.028 | Reference |
| V13 FROZEN | JEV non-VETO | 92.54% | +214.14% | 36.75% | 43.03% | 0.887 | Worse |
| V13 SAFE | JEV non-VETO | 59.63% | +53.62% | 12.45% | 48.67% | 0.501 | Much worse |

### FROZEN definition

Uses score/rank context plus only the 20 features listed in the frozen R5.1 model manifest:

- cs_ret_1b / 2b / 4b / 6b
- cs_rv_6 / 24
- cs_ma_dist_6 / 24
- cs_volume_z_24
- cs_bar_range
- cs_beta24
- cs_residual_ret_6b
- qqq_ret_2b / 6b
- qqq_rv_24
- qqq_ma_dist_24
- ix_trend_qqq
- ix_vol_qqq
- ix_ret1_qqq
- ix_mom6_qqq

### SAFE definition

FROZEN plus additional backward-looking single-asset/QQQ state such as ret_1b/2b/4b/6b, rv, MA distance, volume z-score, beta and residual return. It excludes the identified target-derived universe-return columns.

## Year stability — leakage-safe variants

### V13 FROZEN non-VETO

| Year | Baseline | JEV non-VETO | Mean return of VETOed trades |
|---|---:|---:|---:|
| 2023 | +60.91% | +61.92% | -0.93 bp |
| 2024 | +65.36% | +72.88% | -23.65 bp |
| 2025 | +16.23% | -2.97% | +42.87 bp |
| 2026 YTD | +33.22% | +15.66% | +183.28 bp |

V13 FROZEN mean delta per opportunity (filtered minus baseline): **-2.16 bp**.
Day-block bootstrap 95% CI: **[-5.18 bp, +0.72 bp]**.
Bootstrap probability delta > 0: **7.16%**.

This does not support a JEV veto benefit.

### V13 SAFE non-VETO

The filtered strategy is worse than baseline in every reported full-period risk metric. In 2023, 2024, 2025 and 2026 the average return of VETOed trades is positive, i.e. JEV removes profitable trades on average.

## Invalid high-performance variants and leakage audit

The broader V13 MARKET and V13 UNIVERSE runs produced implausibly high performance. They are **INVALID**.

Direct formula audit of r5_0_1_scored_rows.parquet showed:

- universe_mean_ret equals the cross-sectional mean of future fwd_ret_4b exactly.
- universe_median_ret equals the cross-sectional median of future fwd_ret_4b exactly.
- relative_ret_4b correlates with fwd_ret_4b at approximately **0.917**.
- relative_ret_4b correlation with contemporaneous ret_4b is approximately **0.006**.

Therefore these columns are target/label-family values, not admissible predictor inputs.

The following results are retained only as leakage diagnostics and must never be used for promotion:

- V13 MARKET non-VETO: +2,938% total return — INVALID_LEAKAGE
- V13 UNIVERSE non-VETO: extreme return — INVALID_LEAKAGE

## Additional caveat: historical universe

The canonical-history contract states that the research panel uses a fixed/persistent observed universe and is not a point-in-time historical S&P100.

The available sp100_membership_log.csv currently contains only one 2026-09-01 capture, so 2023-2026 point-in-time S&P100 membership cannot be reconstructed from the present log.

This universe limitation affects the underlying R5.1 historical research panel as well as any JEV overlay using its cross-sectional features.

## JEV probability calibration

Leakage-safe FROZEN diagnostics:

- actual positive-net rate: 47.99%
- mean JEV positive-EV probability: 45.51%
- Brier score: 0.2603

Probability calibration is not yet strong enough for sizing.

## Recommendation

1. Keep JEV_CAN_VETO_LIVE=false.
2. Keep JEV_CAN_SIZE_LIVE=false.
3. Do not use the V1.2 direct score-vs-cost interpretation; R5.1 score is relative alpha, not absolute expected return.
4. Continue only as a prospective shadow experiment if the input contract is cleaned of execution-policy flags and target-derived fields.
5. The next useful JEV hypothesis is macro/event adjudication using truly point-in-time macro features, not re-interpreting the existing R5.1 frozen feature set.
6. Require prospective confirmation before any live authority. The current R5.1 prospective gate is 100 outcomes / 60 distinct days minimum and 150 outcomes / 90 days preferred.

## Reproducibility

Script:
kalman-toss-gateway/research/jev_historical_replay_v1.py

Local research outputs:
/home/taehoon/.local/share/kalman-jev-backtest/results/

AI Gateway spend after the full experiment: approximately $0.5354 against the $1 monthly JEV key budget.
