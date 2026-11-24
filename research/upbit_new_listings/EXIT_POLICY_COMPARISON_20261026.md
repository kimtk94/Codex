# Post-crash 24h Entry and Exit Policy Comparison (2026-10-26)

Research-only local replay on the archived 190-coin seven-day 15-minute OHLCV dataset (artifact 12555802314). Does not touch Kalman LIVE.

Causal entry: first >=20% peak drawdown, four completed 15-minute candles without a new trough, closing price >=3% above trough; additionally price structure, contracting candle range, cooling KRW turnover all pass, entry on next bar open. Only enter within 24 hours by actual UTC timestamps, not by assumed candle count. One entry per eligible market.

Fees 0.05% each side and assumed slippage 0.15% each side; worst-case stop-first for bars crossing multiple thresholds. Comparisons: fixed +20% take/-3% stop; ATR-based initial stop max(3%, 1.5x recent ATR price distance) with +20% take; -3% initial stop plus 10% trailing of the high in completed bars; ATR initial stop and trailing maximum of 10% below high or 2.5x ATR. Stop updates apply only after a candle is complete; no same-bar order advantage is assumed. ALL are research assumptions, not order-book-replay fills.

| Exit | 2023–25 n | Mean net % | 2026 explored n | Mean net % |
|---|---:|---:|---:|---:|
| TP +20 / SL -3 | 77 | +0.0352 | 45 | -0.6931 |
| ATR initial SL / TP +20 | 77 | -2.6173 | 45 | -2.3429 |
| Trailing 10% / initial -3 | 77 | +1.5649 | 45 | -0.3573 |
| ATR initial SL + trailing | 77 | +1.0955 | 45 | -1.2099 |

All medians about -3.2423%; no target of mean +20% met. This is a local exploratory result, not a CI-verified deployment. 2026 has been inspected repeatedly and is not fresh out-of-sample. No delisted markets; potential candle gaps/gap-through stops, execution capacity, intra-15m path and simultaneous positions remain unvalidated. This comparison intentionally excludes re-entry; evaluate bounded re-entry separately without parameter optimization on reused 2026 data. No live-policy modifications.

CSV outputs: `exit_comparison_summary.csv`, `exit_comparison_trades.csv` from local replay.
