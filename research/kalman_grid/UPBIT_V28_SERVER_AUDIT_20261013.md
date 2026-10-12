# Upbit V2.8 server research — 2026-10-13 KST

## Data
- KRW-BTC: 6524 60m candles, 2026-01-01 00:00 UTC to 2026-10-12 02:00 UTC.
- KRW-ETH: 6524 60m candles, same bounds.
- Source: Upbit public KRW candle API; **NOT** Binance BTCUSDT/ETHUSDT.
- Collector: `upbit_history_v28.py`.
- Data path: `/home/taehoon/kalman-data/upbit_grid_research/history_1h/`.
- Sweep: 30 cases, `/home/taehoon/kalman-data/upbit_grid_research/v28_sweep/sweep.csv`.
- Simulated cash 30,000 KRW, per-entry notional 10,000 KRW, 100 candidate levels, hypothetical 0.05% one-way fee, no slippage or orderbook.

| setting | BTC cumulative return | BTC MDD | ETH cumulative return | ETH MDD |
|---|---:|---:|---:|---:|
| static 0.14% | -8.128% | 20.634% | -20.709% | 46.450% |
| rolling 140 bars 0.14% | -18.136% | 35.658% | -27.726% | 51.147% |
| static 1.00% | -7.384% | 20.029% | -17.850% | 44.861% |

### 1-minute data quality blocker
Sample 1m window 2026-10-09 00:00 UTC to 2026-10-12 02:59 UTC:
- BTC 1260 rows / 4500 expected (28.000%), 6 gaps, max gap 541 minutes.
- ETH 1252 / 4500 (27.822%), 14 gaps, max gap 541 minutes.
- Formal audit script: `upbit_data_audit_v28.py`; both marked `BLOCKED_DATA_QUALITY`.
- The collector's `complete=true` only means pagination reached the requested start, **NOT** that all intervals were populated. Do not treat it as market data quality PASS.
- Upbit API does not generate a candle where no trade occurred; nevertheless, consecutive multi-hour gaps in BTC/ETH require independent confirmation, not assumed real market inactivity.

### Risk and interpretation
The hourly results use hypothetical close-based limit fills, ignore Upbit price tick rounding, order book/queue, partial execution, slippage, and actual account fee tier. A true 0.14% intraday-grid performance estimate is therefore **unavailable**.
No production executor or LIVE settings modified. No LIVE orders placed.

Next: independently verify 1m history from a second authorized source; repair missing intervals before trading research, audit hourly coverage/gaps as well, then use complete valid 1m data and exchange-specific cost/tick conventions.
