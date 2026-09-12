# Kalman Quant Tool Priority — 2026-09-12

## Decision

Kalman remains the orchestrator and system of record.

Neon remains authoritative for operational state. Open-source tools are used
selectively behind explicit contracts.

## Priority

1. Qlib concepts / optional Qlib research integration
2. Kalman-native strategy ledger and backtest engine
3. PyPortfolioOpt
4. Riskfolio-Lib
5. QuantConnect LEAN architecture
6. vectorbt research-only validation

## Why

### 1. Qlib
Use for experiment discipline: rolling/walk-forward windows, recorders,
artifacts, metrics, model lifecycle. Do not replace Neon with Qlib storage.

### 2. Kalman-native ledger
This is the production truth for:
signal -> next bar -> fill -> fees/slippage -> position -> PnL -> equity.

No external library should define production execution semantics.

### 3. PyPortfolioOpt
Use first for light portfolio allocation baselines:
equal weight, inverse volatility, HRP, max Sharpe, later Black-Litterman.

### 4. Riskfolio-Lib
Evaluate later for CVaR, risk parity, drawdown and robust optimization.
Keep it in an isolated research environment because its current dependency
stack includes vectorbt.

### 5. LEAN
Borrow architecture, not runtime:
Alpha -> Portfolio Construction -> Risk -> Execution -> Brokerage.

### 6. vectorbt
Keep the existing Market Tools V2 scripts as research-only cross-checks.
Do not make vectorbt a production dependency.

## Required promotion path

RESEARCH -> BACKTEST_PASS -> SHADOW -> PAPER -> LIVE_CANDIDATE -> LIVE

## Phase 1 branch

`feature/quant-stack-v1-20260912`

Phase 1 contains:
- Qlib-style purged walk-forward fold contracts
- Kalman-native long-only reference ledger
- daily-equity performance metrics
- PyPortfolioOpt research adapters
- tests

## Phase 2

- historical feature reconstruction from 2017
- fold-by-fold model training/inference
- model_output backfill
- BUY/SELL/HOLD strategy signal generation
- strategy_backtest_run / strategy_daily_equity / strategy_performance persistence
- Vercel Performance tab from Neon

## Phase 3

- portfolio_target
- order_intent
- broker_order
- execution_fill
- Toss PAPER mode
- hard risk gates and kill switch
