# ETH Grid V3 — Regime-gated research specification (2026-10-18)

## Evidence and selection
Source: GitHub Actions real-data Run 39120651192 (27 completed strict OHLC combinations). This is an exploratory in-sample parameter comparison, not an out-of-sample estimate of future profit.

| spacing | levels | 2024 return | 2025 return | 2026 YTD return | worst yearly/YTD return | worst within-period MDD |
|---|---:|---:|---:|---:|---:|---:|
| 1.0% | 100 | 30.3025% | 0.3355% | -5.7916% | -5.7916% | -51.6868% |
| 1.5% | 100 | 35.6616% | 5.3264% | -6.4471% | -6.4471% | -47.3003% |
| 1.5% | 50 | 29.4335% | -12.0800% | -10.3320% | -12.0800% | -52.0555% |

Neither candidate passes a 10% annual return target across observed intervals; neither passes a conservative MDD gate.

## Proposed next experiment (not yet implemented)
1. Preserve original strict 1-minute OHLC simulator as baseline; do not rewrite production logic.
2. Construct higher-timeframe regime features using only bars **closed before** each decision time: 1D EMA50/EMA200 or 20/60-day return, ATR/realized volatility and price trend. Do not use the current unfinished day's final candle.
3. Evaluate gating alternatives: `always_on`, `no_new_buys_in_downtrend`, `flat_in_downtrend` (with explicit exit fees), and `volatility_pause`.
4. Preserve order/cash reservation accounting during any entry inhibition or cancellation; record gross exposure, time in market, trade count, fee totals, worst MDD, and return.
5. Fix all thresholds using training dates only. Out-of-sample window(s) and parameter choices must be predefined before test results are read.
6. Compare alongside ETH buy-and-hold and a 50/50 ETH/KRW benchmark at matching initial capital and observation dates.
7. Stress test historical tick sizes, fees, spread, unfilled limits, missing-minute gaps, and partial fills.
8. Refuse LIVE deployment until loss controls, data leakage checks and walk-forward results pass.

## Data integrity blockers
- Earliest verified local minute-bar range previously reported starts 2023-12-31 15:00 UTC, not 2020. Backfill earlier history before making 2020-2023 claims.
- 2026 is a partial year, latest verified market data through Oct 14, 2026.
- Regime conditioning needs an explicit warm-up period before 2024; do not backfill signals from future candles.
- Results for all 27 combinations were observed in the Actions logs, but the first sweep artifact was absent due to an upload path mismatch. Fix committed and rerun initiated; artifact confirmation is still pending.

## No operational authorization
This document does not change Kalman LIVE, place orders, or authorize trading. All research should remain isolated and read-only.
