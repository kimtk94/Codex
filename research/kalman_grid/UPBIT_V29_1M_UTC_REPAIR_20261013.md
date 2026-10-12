# V2.9 Upbit 1-minute UTC repair and smoke comparison

Date: 2026-10-13 KST. PAPER ONLY.

## UTC defect repaired
`upbit_history_v28.py` now interprets timezone-naive API candle timestamps as UTC, not the server local timezone. Fix commit: `a30bb8cd53b1920b4bdd03d145b5c276595a2983`.

## Independent data re-collection
- `/home/taehoon/kalman-data/upbit_grid_research/utcfix_1m/KRW-BTC_1m_history.csv`: 4,500 of 4,500 expected one-minute slots, continuity PASS.
- `/home/taehoon/kalman-data/upbit_grid_research/utcfix_1m/KRW-ETH_1m_history.csv`: 4,483 of 4,500 slots (99.622%), max gap 2m, quality gate PASS; 17 isolated missing candles require venue-side/no-trade cross-check.
- Window: UTC 2026-10-09 00:00 to 2026-10-12 02:59, 75 hours.
- Old CSV retained unchanged. The previously reported 541-minute gaps were artifacts of incorrect timezone parsing.
- Quality checker: `upbit_data_audit_v28.py`.

## Corrected 1m CLOSE-only exploratory grid smoke
Settings: cash 30,000 KRW, per-order 10,000 KRW, hypothetical one-way 0.05% fee, grid levels 100, no spread/slippage/tick-size/queue model. Rolling intervals measured in **1-minute observations**, NOT hours.

| Market | Mode | Gap | 75h cumulative return | MDD |
|---|---|---:|---:|---:|
| BTC | Static | 0.14% | 0.000% | 0.000% |
| BTC | Rolling 140 observations | 0.14% | -0.010% | 0.528% |
| BTC | Rolling 700 observations | 0.14% | +0.067% | 0.353% |
| ETH | Static | 0.14% | +0.186% | 0.261% |
| ETH | Rolling 140 observations | 0.14% | +0.373% | 0.585% |
| ETH | Rolling 140 observations | 0.50% | +0.533% | 0.261% |

0.000% with 0.000% MDD could represent no fills/cash and should not be treated as a stable low-risk trading result.

### Critical limitations
Short 75h window; no model of true intraminute execution, orderbook spread/depth, slippage, Upbit tick-size rounding, exchange order sizing, partial fills, stop/exit conditions, regime effects, outages. This is NOT sufficient to conclude net profitability or suitability for LIVE trading. Rebalance periods are observation counts and cannot be compared directly with 1-hour rebalance periods.

## Next steps
1. Obtain several months to years of continuous venue-specific 1m data, validate no-trade candle rules and missing intervals.
2. Build Upbit-specific tick size, min-notional, fee profile and historical maker/taker sensitivity.
3. Simulate intraminute fill uncertainty, partial fills and orderbook effects; run walk-forward splits.
4. Compare BTC/ETH equal-dated gross vs net returns, turnover, win rate, MDD, exposure and no-fill rate.
5. Keep PAPER/Shadow separate; no LIVE changes or orders.
