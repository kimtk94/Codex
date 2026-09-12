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
-> portfolio risk adjustment
-> order_intent
-> order safety gate
-> SHADOW broker_order
-> execution_fill
-> execution ledger snapshot
```

## Tool policy

1. Qlib semantics / optional research integration
2. Kalman-native strategy ledger
3. PyPortfolioOpt
4. Riskfolio-Lib isolated evaluation
5. LEAN-inspired execution contract (architecture reference only)
6. vectorbt research-only cross-check

Qlib does not replace Neon. vectorbt does not define production execution
semantics.

## Qlib Recorder integration

Qlib is now connected as an **optional experiment recorder** only.

Install it into the research environment:

```bash
/opt/kalman/.venv-research-v2/bin/pip install \
  -r /opt/kalman/app/research/quant_stack/requirements-qlib.txt
```

Enable it for historical runs:

```bash
export KALMAN_QLIB_ENABLED=true
sudo -E /opt/kalman/app/scripts/run_historical_quant_v1.sh
```

Default local server paths:

```text
/opt/kalman/state/qlib_mlruns
/opt/kalman/state/qlib_provider
```

Qlib records experiment parameters, numeric performance metrics and a compact
artifact manifest. Kalman remains authoritative for source data, fold outputs,
signals, fills, ledger and PnL.

The adapter uses an SQLite MLflow tracking backend (`qlib_mlflow.db`) inside
the configured tracking root. This avoids the MLflow 3.x filesystem-tracking
maintenance mode and also avoids the Qlib 0.9.7 absolute file-URI lock-path
issue.

## PyPortfolioOpt portfolio targets

PyPortfolioOpt is connected above the market-level Kalman-native ledgers.

```text
US historical_equity
KR historical_equity
BTC historical_equity
        ↓
daily sleeve returns
        ↓
rolling lookback (default 180 days)
        ↓
PyPortfolioOpt HRP
        ↓
monthly portfolio_target
        ↓
combined portfolio equity
```

Install the research dependency:

```bash
/opt/kalman/.venv-research-v2/bin/pip install \
  -r /opt/kalman/app/research/quant_stack/requirements-pypfopt.txt
```

The server runner enables this research portfolio layer by default. Configure it
with:

```bash
export KALMAN_PORTFOLIO_ENABLED=true
export KALMAN_PORTFOLIO_METHOD=hrp
export KALMAN_PORTFOLIO_LOOKBACK_DAYS=180
export KALMAN_PORTFOLIO_MIN_OBSERVATIONS=90
export KALMAN_PORTFOLIO_REBALANCE=M
```

Outputs:

```text
historical_quant_v1/portfolio/
  portfolio_target.parquet
  portfolio_equity.parquet
  portfolio_performance.json
```

Portfolio weights are research targets only. They never call Toss and are not
written to Neon production tables by this runner.

## Riskfolio-Lib benchmark layer

Riskfolio-Lib is connected as an isolated **benchmark-only** layer. It does not
replace the PyPortfolioOpt HRP target and it never creates broker orders.

CI installation of Riskfolio-Lib 7.3.0 confirmed that its current dependency
tree pulls `vectorbt>=0.28.0` (the tested environment resolved vectorbt 1.1.0).
For that reason Riskfolio stays in a separate venv and neither Riskfolio nor
vectorbt defines Kalman's production execution semantics.

Benchmarks:

```text
CVaR MinRisk
MV Risk Parity
CDaR MinRisk
```

Install into its own environment:

```bash
python3 -m venv /opt/kalman/.venv-riskfolio
/opt/kalman/.venv-riskfolio/bin/pip install \
  -r /opt/kalman/app/research/quant_stack/requirements-riskfolio.txt
```

Server behavior defaults to `auto`: when the isolated venv exists and can
import `riskfolio`, benchmarks run after the historical experiment and
validation. Otherwise the benchmark is skipped without breaking the main
research pipeline.

Configuration:

```bash
export KALMAN_RISKFOLIO_ENABLED=auto   # auto / true / false
export KALMAN_RISKFOLIO_VENV=/opt/kalman/.venv-riskfolio
export KALMAN_RISKFOLIO_LOOKBACK_DAYS=180
export KALMAN_RISKFOLIO_MIN_OBSERVATIONS=90
export KALMAN_RISKFOLIO_REBALANCE=M
```

Outputs:

```text
historical_quant_v1/riskfolio/
  portfolio_target_cvar_minrisk.parquet
  portfolio_target_risk_parity.parquet
  portfolio_target_cdar_minrisk.parquet
  portfolio_equity_*.parquet
  portfolio_performance_*.json
  riskfolio_comparison.csv
  riskfolio_summary.json
```

The comparison file also includes the PyPortfolioOpt HRP baseline when its
performance artifact exists.

## LEAN-inspired execution contract

Kalman now uses the **separation-of-concerns pattern** from QuantConnect LEAN's
Algorithm Framework as an architecture reference. LEAN itself is not installed
or imported by this package.

The research flow is:

```text
PortfolioTarget
    ↓
portfolio risk adjustment
    ↓
OrderIntent
    ↓
order safety gate
    ↓
BrokerOrder (SHADOW only)
    ↓
ExecutionFill (SHADOW NAV fill)
    ↓
execution ledger snapshot
```

This preserves two distinct risk layers:

1. Portfolio-level risk changes requested target weights before execution.
2. Order-level safety gates approve or reject the resulting intents immediately
   before a broker order can exist.

The v1 broker is intentionally hard-coded to `SHADOW`. LIVE mode is rejected
before broker-order creation, and there is no Toss import or network call in
the research execution module. The existing Toss Gateway remains a separate
production boundary.

No-lookahead semantics are explicit:

- planning/reference NAV: latest observation **strictly before** `effective_ts`
- shadow fill NAV: first observation **on or after** `effective_ts`

Enable or disable the post-portfolio execution-contract runner with:

```bash
export KALMAN_LEAN_EXECUTION_ENABLED=true
```

Outputs:

```text
historical_quant_v1/execution/
  portfolio_target_risk_adjusted.parquet
  order_intent.parquet
  broker_order.parquet
  execution_fill.parquet
  execution_ledger.parquet
  execution_status.json
```

These artifacts are research-only. They do not write to Neon and do not submit
orders to Toss.

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
pytest -q \
  tests/test_quant_stack.py \
  tests/test_historical_backfill.py \
  tests/test_quant_artifact_validation.py

# optional Qlib integration smoke test
pip install -r research/quant_stack/requirements-qlib.txt
pytest -q tests/test_qlib_recorder.py

# PyPortfolioOpt portfolio target smoke test
pip install -r research/quant_stack/requirements-pypfopt.txt
pytest -q tests/test_pypfopt_portfolio_targets.py

# Riskfolio isolated benchmark smoke test
pip install -r research/quant_stack/requirements-riskfolio.txt
pytest -q tests/test_riskfolio_benchmarks.py

# LEAN-inspired execution contract smoke test
pytest -q tests/test_lean_execution_contract.py
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
