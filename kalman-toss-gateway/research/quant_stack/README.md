# Kalman Quant Stack v1

This package is research-only and must not call Toss or write to production
execution tables.

## Flow

```text
market_price / market_feature_store
-> existing Model V2 feature matrix
-> purged walk-forward folds
-> train / validation model selection
-> prospective test-only model_output
-> BUY / SELL / HOLD decisions
-> Kalman-native next-bar ledger
-> daily equity / metrics
-> portfolio allocation
```

## Tool policy

1. Qlib semantics / optional research integration
2. Kalman-native strategy ledger
3. PyPortfolioOpt
4. Riskfolio-Lib isolated evaluation
5. LEAN architecture reference
6. vectorbt research-only cross-check

Qlib does not replace Neon. vectorbt does not define production execution
semantics.

## Historical backfill

The historical engine deliberately reuses the current Model V2 rules:

- training-only feature selection
- median imputation
- standard scaling
- L2 logistic regression
- balanced class weights
- C selected on validation ROC-AUC, then Brier score
- probability threshold selected on validation balanced accuracy
- purge gap equals the market forecast horizon by default
- only TEST-window probabilities become historical model output

The decision layer is stateless:

- probability >= entry threshold -> BUY
- probability <= 1 - entry threshold -> SELL
- otherwise -> HOLD

Actual position state belongs only to the native ledger.

## Server command

From the deployed app:

```bash
sudo /opt/kalman/app/scripts/run_historical_quant_v1.sh
```

Defaults:

```text
start       2017-01-01
train       504 observations
validation   63 observations
test        126 observations
max hold     20 bars
```

Output:

```text
$KALMAN_DATA_ROOT/Market_Model_V2/historical_quant_v1/
  us/
  kr/
  btc/
  historical_experiment_status.json
```

Each market directory contains:

```text
historical_model_output.parquet
historical_strategy_signal.parquet
fold_metrics.json
experiment.json
historical_trades.parquet
historical_equity.parquet
historical_performance.json
run_summary.json
```

The ledger refuses to synthesize fills from close prices when the original
anchor OHLC artifact is missing. `--allow-close-fallback` exists only for
explicit smoke tests.

## Quick test

From `kalman-toss-gateway`:

```bash
pytest -q tests/test_quant_stack.py tests/test_historical_backfill.py
```

GitHub Actions also runs these tests on the quant-stack feature branch.

## Neon

`neon_backtest_contract.sql` is a schema proposal only. It is not applied
automatically.

Backtest trades must remain separate from production `strategy_ledger`.

## Design constraints

- Strict next-bar execution only.
- No look-ahead.
- Purged walk-forward validation.
- Fees and slippage are explicit.
- Intraday equity is resampled to daily before annualized risk metrics.
- BACKTEST / SHADOW / LIVE remain explicit and separate.
- Production broker calls are outside this package.
