# Kalman Grid V2.5 — research / PAPER ONLY

This isolated research package models static and rolling grid levels. It is **not** connected to Kalman LIVE, any broker API, or order execution.

## Core components
- `v25_research.py`: rolling-center grid and QQQ/QLD Parquet scenario sweep
- `kalman_grid_v23.py`: price-observation strategy adapter
- `kalman_grid_v22/order_ledger.py`: Decimal-based order ledger
- `test_v25.py`: recenter tests

## Default parameters
Spacing: 0.14%, candidate levels: 100, capital/exposure cap: 30,000 (simulation units), buy notional: 10,000. Evaluation intervals: 0 (static), 140, and 700 bars. The research code uses the numbers as **simulated units**, not verified KRW-to-USD conversions.

## Running
Install pandas and pyarrow. From this directory:

```bash
python3 -m unittest -v test_v25.py
python3 v25_research.py \
  --data-dir /home/taehoon/kalman-data/assets-1h \
  --out-dir /home/taehoon/kalman-data/grid_v25_research
```

Both data files should be named `QQQ_1h_2017plus.parquet` and `QLD_1h_2017plus.parquet` and contain `t` and `c` columns.

## Limitations
Hourly close snapshots do not establish intrabar limit order chronology. No FX, spread, slippage, tax, tick/lot sizes, partial exchange fills, historical adjustment audit, or live reconciliation are modeled. High frequency grid returns should not be considered realistic live performance.

This branch is intentionally independent of the dirty production worktree. Do not merge into LIVE without an explicit production review.
