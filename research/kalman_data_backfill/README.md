# Kalman US ETF raw-data gap audit and SIP staged backfill

Audits NYSE regular-hours QQQ/QLD SIP 15-minute and daily Parquet files already in the US_ETF/raw/ Google Drive folder. It uses the NYSE exchange calendar for holidays, DST transitions, weekends, and early closes. Identifies both trailing and interior historical gaps.

## Safety contract

- Existing source Parquets are read-only. No Drive writes, live-trading changes or model deployment.
- --fetch uses Alpaca feed=sip, adjustment=all to fetch months containing missing timestamps. Stages only missing timestamps as proposed_additions.parquet; never merges or overwrites original data.
- Requires a Drive Viewer service account for four existing sources. Optional fetch additionally requires ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY repository secrets with historical SIP entitlement.
- Workflow artifact contains summary.json, missing_bars.csv, and optional unfilled_gaps.csv ONLY. Licensed SIP-priced proposed_additions.parquet is staged on the ephemeral runner and is NOT publicly uploaded. A separate approved private Drive persistence step is required before it can be used. 24-month query cap prevents unconstrained API pulls.
- File modification time does not prove last OHLC candle timestamp; the audit reads source data.
- Newly staged quote_volume is an estimate (Alpaca VWAP times volume), not directly measured trade notional.

## Run in GitHub

Actions -> Kalman US ETF Raw Gap Audit & Staged Backfill -> Run workflow. First run fetch_missing=false for read-only audit and review the output artifact. Then rerun with fetch_missing=true to check whether SIP can supply gaps, without changing source. Price data is not uploaded to public Actions artifacts.

## Local use

Install pandas requests exchange-calendars pyarrow.

    python research/kalman_data_backfill/audit_stage.py --dataset QQQ:15m:/path/QQQ_15m_raw.parquet --dataset QLD:15m:/path/QLD_15m_raw.parquet --dataset QQQ:1d:/path/QQQ_1d_raw.parquet --dataset QLD:1d:/path/QLD_1d_raw.parquet --as-of 2026-10-29 --out-dir outputs/us_gap_audit

## Promotion gates

1. OHLC rows valid and duplicate-free; session timestamps aligned with XNYS.
2. Confirm adjusted price and provenance; do not mix IEX and SIP silently.
3. Preserve source file hashes and versions; stage candidates never replace original timestamps.
4. Only in a separately approved process, merge and re-audit complete rows; explain market-halt/no-trade exceptions.
5. Use purged walk-forward, fees, realistic stop/TP ordering and slippage for any model. This workflow does not touch LIVE.

## Proposed model research universe (not live)

See recommended_universe_v1.json for 24 candidates: 20 US ETFs/equities, 4 core Upbit KRW pairs, plus a dynamic historical new-listing event cohort. The list deliberately separates execution instruments from market-regime features. Selection is not a claim of profitability or a completed liquidity screen. Inputs with unverified coverage remain candidates; current-only S&P 100 snapshots must not be used as historical constituents. Universe model contracts are checked by test_universe.py.
