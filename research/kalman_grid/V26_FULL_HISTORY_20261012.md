# Kalman Grid V2.6 — full-history server research run (2026-10-12)

**Status:** execution complete; scientific/trading validation **NOT PASS**.

## Source / environment
- Branch: `research/kalman-grid-v25-20261012`
- Server independent clone: `/home/taehoon/kalman-grid-v26-benchmark`
- Data: `/home/taehoon/kalman-data/assets-1h/{QQQ,QLD}_1h_2017plus.parquet`
- Output: `/home/taehoon/kalman-data/grid_v26_research/sweep.csv`
- QQQ: 13,112 hourly bars, 2020-07-27 to 2026-08-28.
- QLD: 10,233 hourly bars, same outer date window.
- Strategy scenarios: 2 assets × 3 anchor schedules (static/140/700 bars) × 5 spacings = **30**.
- Tests: 12/12 discovered + 10/10 additional ledger tests passed.
- Main improvements: `active_ids` index for active-order reservations; fast per-bar audit while retaining `audit()` full historical audit; 12-decimal purchase quantity rounding.

## Selected cumulative results (not annualized)
| Strategy | QQQ return | QQQ MDD | QLD return | QLD MDD |
|---|---:|---:|---:|---:|
| Static, 0.14% | +0.200% | 0.639% | +0.959% | 11.633% |
| Rolling 140, 0.14% | +4.199% | 33.117% | -2.066% | 59.548% |
| Rolling 700, 0.14% | +4.169% | 22.109% | -3.345% | 59.594% |
| Rolling 140, 0.50% | +23.927% | 28.775% | +16.654% | 36.590% |
| Rolling 140, 1.00% | +40.193% | 28.281% | +29.940% | 50.940% |

## Critical limitations and unresolved issues
These are **hourly-close-observation** simulations, NOT valid trade-fill reconstructions. A resting limit order cannot be assumed to execute at a grid limit price merely because the close crossed the level; missing intrabar chronology, spread, slippage, market sessions, and price/quantity tick restrictions. The notional and cash numbers are only simulation units; **no KRW/USD FX model**. Missing corporate action adjustment audit and matched timestamp coverage. The model uses fixed-size reserved order cash including fee; realistic order quantity and exposure must be checked against broker constraints. Equal starting cash with differing monthly time coverage is not a like-for-like OOS comparison.

**No strategy passed an annualized net-return >10% plus acceptable MDD live gate. Do not deploy.**

Next: validate full ledger invariants at checkpoints, introduce fill-path sensitivity bounds using open/high/low/close, properly model USD/KRW and costs, align sessions, then run OOS + walk-forward. Never modify production executor/config during research.
