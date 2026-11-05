# Kalman Market Tool Lab — nine-tool research plan

This repository branch contains an **offline, read-only baseline**, not nine installed tools or executed market-data imports. No broker credentials, production changes, paid APIs or LIVE trading.

## Common stages
1. Normalize vendor data to `timestamp` (UTC timezone-aware), `symbol`, `open`, `high`, `low`, `close`, `volume`, plus `data_asof` and provenance metadata.
2. Verify timestamps, splits, adjusted/unadjusted prices, missing sessions, free-tier limitations and data availability at decision time.
3. Time-split walk-forward train/validation/test, with purging/embargo when labels overlap. Keep final test set untouched.
4. Use frozen Kalman baseline, realistic costs, fills, and fixed exposure limits; report net return, MDD, trades, Sharpe, directional accuracy, and by-regime deltas.
5. Only after clean evidence consider Shadow-only integration; LIVE remains unchanged.

## Projects (priority and gates)
| Tool | Role | Pilot | Gate |
|---|---|---|---|
| OpenBB | Price/fundamentals providers | Compare daily QQQ/QLD/SPY/TQQQ vs existing Alpaca bars | provider access and adjustment parity |
| Daily Stock Analysis | News summaries | Timestamped report ingest on a fixed historical sample | no hindsight or post-event content |
| VectorBT | Parameter sweeps | Reproduce existing 3%/3% 4-day Triple Barrier on deterministic samples | intrabar order/fees match reference |
| Qlib | Alpha forecasting | LightGBM on shared date-split aligned features | no leakage + OOS incremental Sharpe |
| Kronos | Candlestick forecasts | GPU shadow inference on 15min/1h OHLCV in Colab | model train-period contamination audit |
| TradingAgents | LLM committee | Fixed JSON schema, replay archived point-in-time inputs | API spend capped; baseline outperform |
| AI Hedge Fund | LLM committee comparator | Same frozen historical snapshots as TradingAgents | timestamps, pricing, API spend |
| NautilusTrader | Event fill simulation | Match fee/slippage fill rules on 1min trades | benchmark vs current event engine |
| Freqtrade | Crypto backtest | Separate Upbit 15min cohort from PR #262 | listing/delisting universe and execution model parity |

## Guardrails
- No external trade/order APIs or credentials in CI.
- No untrusted agent access to `kalman-toss-gateway` or production secrets.
- Providers must be explicitly configured: do not claim current data available by merely importing OpenBB.
- Heavy GPU and paid LLM runs are manual, cost gated, and isolated.
- `ohlcv_audit.py` only validates a uniform candle CSV, not the historical exports' existing schemas.

## Next acceptance criteria
- Real existing CSV schemas mapped into canonical input using dedicated adapters.
- Upstream project identity/license/releases independently verified.
- Per-tool pinned dependency lockfiles in separate CI jobs, no mixed environment.
- All 9 tools produce reproducible evaluation artifacts, or explicit BLOCKED with reason.
