# Kalman R6 Selective-Horizon Research Benchmark

**Status:** research only  
**Date:** 2026-09-22  
**Production model:** `R5.1_BASE_HGB` remains unchanged.

## Why this is a second-stage R6 layer

The frozen R5 tournament already tested HGB, CatBoost YetiRank, XGBoost pairwise ranking, sector-neutral variants, and a rank ensemble under the same Top1 / volatility-target / 10 bp / exact +4 bucket / non-overlap contract.

The historical result was decisive: `R5C0_HGB_REFERENCE` was the only survivor. YetiRank, pairwise XGBoost and the ensemble all had negative cumulative OOS returns. R6 therefore does not repeat the ranker search.

R6 keeps R5 HGB as the stock selector and tests three incremental layers:

1. **Selective entry / meta-labeling** — estimate whether an already-selected R5 Top1 trade should be skipped.
2. **Walk-forward exit horizon** — select among 2/4/6/8 canonical 60-minute buckets using prior OOS evidence only.
3. **Market-context conditioning** — allow QQQ/universe state variables to influence abstention probability, without introducing a new hard regime rule.

## Prior evidence incorporated

R5.2 macro ablation already showed that macro variables should not be promoted into the stock selector. R5.3 macro risk overlays improved drawdown modestly but sacrificed growth and failed the formal promotion gate.

Accordingly, R6 v1 does not add macro/news features. Context is restricted to already-frozen decision-time QQQ and universe variables.

## Source lineage

Primary R5 OOF panel:

`US_ETF/model_lab_v1/results/r5_0_1_research_sandbox_all_data/r5_0_1_scored_rows.parquet`

Canonical 1h history:

`US_ETF/directional_research/canonical_history_v1/panel_1h_gap_aware/<SYMBOL>_1h_gap_aware.parquet`

The R5 score is a **relative 4h alpha forecast**, not a probability.

## Arms

- `R5_BASE_4H`: frozen R5 Top1, 10 bp weighted cost, +4 expected-seq, non-overlap.
- `R6A_CORE_SELECTIVE50_4H`: R5 selector + 50% coverage meta-label abstention.
- `R6A_CONTEXT_SELECTIVE50_4H`: same, with QQQ/universe context.
- `R6B_CORE_SELECTIVE50_WF_HORIZON`: core abstention + walk-forward horizon.
- `R6C_CONTEXT_SELECTIVE50_WF_HORIZON`: context abstention + walk-forward horizon. This is the designated primary R6 candidate.
- 25% and 75% context coverage arms are diagnostics only.

## Leakage controls

- Base R5 scores are frozen out-of-fold scores.
- A meta test fold can only train on prior decisions whose +4h target is fully observed before the test fold.
- The latest 25% of prior decisions is reserved as a calibration tail.
- Isotonic calibration and the 50% coverage threshold are fit on that prior calibration tail only.
- Test-fold outcomes never set the probability threshold.
- Test-fold outcomes never choose the exit horizon.
- Future/target/forward-return columns are forbidden as meta-model inputs.
- The reconstructed 4h canonical return is audited against the frozen R5 target; the baseline itself uses the frozen R5 return.

## Primary metrics

The benchmark reports:

- executed trades
- cumulative net return
- net log growth
- mean/median return per trade
- win rate
- profit factor
- maximum drawdown
- fold-level results
- paired moving-block bootstrap of daily log-growth difference vs R5

Win rate is secondary to positive net expected value and log growth.

## Promotion gate

`R6C_CONTEXT_SELECTIVE50_WF_HORIZON` is research-promotion eligible only if all checks pass:

- >=300 OOS trades
- log growth > matched R5 baseline
- profit factor >= baseline
- win rate >= baseline
- MDD no worse than baseline by more than 2 percentage points
- positive paired fold improvement in at least 5 evaluable folds
- paired daily-log bootstrap 95% lower bound > 0

Passing this gate does **not** enable live trading. It only supports a separate prospective-shadow phase.

## Safety boundary

The R6 module does not:

- import or call Toss
- write Neon
- modify `.env`
- modify cron
- change `AUTO_TRADE_SIGNAL_POLICY`
- replace `R5.1_BASE_HGB`

## Run on the Kalman server

```bash
cd /opt/kalman/app
export KALMAN_ENV_FILE=/opt/kalman/.env
/opt/kalman/.venv/bin/python research/r6_selective_horizon.py
```

Outputs are written to:

`US_ETF/model_lab_v1/results/r6_selective_horizon/`

including `r6_metrics.csv`, `r6_fold_metrics.csv`, meta OOS CSVs, `r6_research_report.json`, and `r6_manifest.json`.
