# Kalman Grid V3.1: Upbit September holdout — 2026-10-13

Research only; no live trading.

Source: Upbit public KRW 1-minute candles. Independent sample: 2026-09-01 00:00 UTC to 2026-09-03 23:59 UTC (72 hours). Raw files: `/home/taehoon/kalman-data/upbit_grid_research/v31_sep_pilot/`.

| Data quality | KRW-BTC | KRW-ETH |
|---|---:|---:|
| Expected minute slots | 4320 | 4320 |
| Actual candles | 4319 | 4316 |
| Coverage | 99.977% | 99.907% |
| Largest observation gap | 2min | 2min |
| Quality checker result | PASS | PASS |

## 1-minute close-observation model
30,000 KRW starting cash; 10,000 KRW notional/order; 100 theoretical levels; assumed 0.05% fee each side; no exchange tick-size rounding, spread, slippage, queue/fill modeling or corporate-action adjustment. Returns are **72h cumulative**, not annualized.

| Market | Spacing | Static return / MDD / fills | Rolling700 return / MDD / fills |
|---|---|---|---|
| BTC | 0.14% | +0.1065% / 2.0293% / 16 | +0.1485% / 2.3983% / 24 |
| BTC | 0.50% | +0.2665% / 1.7994% / 4 | +0.3640% / 1.6930% / 5 |
| BTC | 1.00% | +0.8995% / 1.3369% / 6 | +0.2998% / 0.7825% / 2 |
| ETH | 0.14% | +0.2263% / 4.3232% / 34 | +0.2100% / 4.3887% / 38 |
| ETH | 0.50% | +0.3998% / 2.6716% / 6 | +0.8811% / 2.6509% / 13 |
| ETH | 1.00% | +0.5997% / 2.3056% / 4 | +0.5997% / 2.3769% / 4 |

Compare October's 11-day sample separately; **do not stitch disconnected September/October samples or extrapolate short-term returns**. Next prioritize months/years of high-quality contiguous data, proper Upbit exchange fee/tick simulation, aligned out-of-sample periods, cost sensitivity and rigorous full-audit checks. Never deploy to LIVE.
