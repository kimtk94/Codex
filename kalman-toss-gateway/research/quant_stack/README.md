# Kalman Quant Stack v1

This package is research-only and must not call Toss or write to production
execution tables.

## Flow

market_price / market_feature_store
-> walk-forward folds
-> model training + inference
-> model_output
-> strategy signal
-> native ledger
-> daily equity / metrics
-> portfolio allocation

## Tool policy

- Qlib: semantics first, optional library later.
- PyPortfolioOpt: allowed in research v1.
- Riskfolio-Lib: phase 2 evaluation only.
- LEAN: architecture reference only.
- vectorbt: existing research-only validation path only.

## Quick test

From `kalman-toss-gateway`:

```bash
pytest -q tests/test_quant_stack.py
```

## Design constraints

- Strict next-bar execution only.
- No look-ahead.
- Fees and slippage are explicit.
- Intraday equity is resampled to daily before annualized risk metrics.
- BACKTEST / SHADOW / LIVE must remain explicit and separate.
- Production broker calls are outside this package.
