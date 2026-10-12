# Kalman Grid V3.2 — September 2026 complete month Upbit KRW 1m

Status: **DATA VALIDATION PASS; MONTHLY STRATEGY METRICS NOT YET VERIFIED**.

## Observed server files
- Data root: `/home/taehoon/kalman-data/upbit_grid_research/v32_sep_full/`.
- Requested window: 2026-09-01T00:00:00Z to 2026-10-01T00:00:00Z (43,200 expected minutes per instrument).
- KRW-BTC: 43,197 minute candles; coverage 99.993%; 3 missing minutes, 3 gaps, max gap 2 minutes. Start 2026-09-01T00:00:00Z, last 2026-09-30T23:59:00Z.
- KRW-ETH: 43,165 candles; coverage 99.919%; 35 missing minutes across 34 gaps, max gap 3 minutes. Same start and last timestamps.
- Audits: `upbit_data_audit_v28.py`, both PASS.
- Public Upbit minute candles, UTC fixed collector, read-only. No live execution, no keys.
- Collected on independent clone `/home/taehoon/kalman-grid-v30-research`, not Kalman LIVE tree.
- Previous first-three-days September results are NOT full-month returns; do not conflate them.

## Strategy run status
A full-month strategy comparison was attempted but output not verified. Desktop Commander monthly quota was exhausted while reading process output. **Do not claim a September monthly return / Sharpe / MDD / trade count.** Keep status pending until output read and persisted.

## Next
- Independently verify results and write machine-readable CSV/manifest (do not rely on stdout).
- Confirm ETH 35 missing minute slots are Upbit no-trade bars vs collection issues.
- Add Upbit minimum notional, tick sizes, slippage, effective maker/taker fees.
- Fetch and validate additional complete months, run true out-of-sample monthly and yearly returns, compare buy-and-hold/cash, profit/MDD and active exposure.
- Retain research PAPER-only isolation and LIVE freeze.
