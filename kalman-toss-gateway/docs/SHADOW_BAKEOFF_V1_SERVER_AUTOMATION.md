# Kalman Forward SHADOW Bake-off V1 — Server Automation

Status: RESEARCH / FILE-ONLY
Branch: `feature/shadow-bakeoff-v1-20260913`

## Purpose

Track three forward portfolio allocators on new data without sending orders:

- A — Hybrid + Equal Weight
- B — Hybrid + Static Max Sharpe
- C — Hybrid + `risk_cap_110`

Hybrid sleeves:

- US — V2 nested final-refit
- KR — V3 return-regime final-refit
- BTC — V2 nested final-refit

Kalman Native Ledger remains authoritative.

## Safety invariants

The scheduled workflow is fail-closed:

- `production_write=false`
- `neon_write=false`
- `toss_execution=false`
- `live_execution=false`
- `auto_trade_visible=false`
- `dashboard_snapshot_created=false`

It refuses to run research scoring while `TRADING_ENABLED=true` or
`LIVE_TRADING_CONFIRM` is set.

## Canonical scheduled flow

```text
run_shadow_bakeoff_daily.sh
  |
  +-- current Market Data V2 refresh
  +-- current Features V2 refresh
  +-- optional historical integrated source refresh hook
  +-- source_freshness.py
       |
       +-- stale -> WAITING_SOURCE_REFRESH, exit 0
       |
       +-- fresh -> run_shadow_bakeoff_v1.sh
                     |
                     +-- historical matrix refresh if source files changed
                     +-- US/BTC V2 final-refit scorer
                     +-- KR V3 final-refit scorer
                     +-- Native Ledger replay
                     +-- A/B/C portfolio recomputation
                     +-- file-only status/history artifacts
```

## Historical integrated source contract

The bake-off forward scorer uses the validated 2017+ integrated sources:

```text
Market_Data/v2/raw/historical_2017/
  multimarket_raw_2017_present.parquet

Market_Features/v2/talib/historical_2017/
  multimarket_features_2017_present_v0_3.parquet
```

The ordinary Market Data V2 / Features V2 refresh does **not** automatically
rewrite these integrated historical files.

Therefore the scheduler has a hard freshness gate. Until all US/KR/BTC anchor
series and the integrated feature table have advanced beyond the fixed seed,
the scheduled job reports `WAITING_SOURCE_REFRESH` and does not manufacture
new forward evidence.

An optional validated source builder can be attached using:

```bash
KALMAN_SHADOW_BAKEOFF_SOURCE_REFRESH_SCRIPT=/path/to/validated_refresh.sh
```

The value may be placed in `/opt/kalman/.env`; cron reads it from that file.

## Install

After the branch is deployed to `/opt/kalman/app`:

```bash
cd /opt/kalman/app
sudo /bin/bash scripts/install_shadow_bakeoff_v1_cron.sh --install
sudo /bin/bash scripts/install_shadow_bakeoff_v1_cron.sh --show
```

Installed schedule:

```text
Tue-Sat 08:10 Asia/Seoul
```

The daily runner refreshes the current V2 market/feature snapshots itself, so
it does not rely on another cron entry having completed first.

## Manual smoke

```bash
cd /opt/kalman/app
/bin/bash scripts/run_shadow_bakeoff_daily.sh
```

Expected pre-source-refresh result:

```text
SHADOW_BAKEOFF_WAITING_SOURCE_REFRESH
```

Expected once integrated sources advance:

```text
BAKEOFF_SAFETY_INVARIANTS=PASS
SHADOW_BAKEOFF_DAILY_COMPLETE
```

## Health

```bash
/bin/bash /opt/kalman/app/scripts/check_shadow_bakeoff_v1.sh
```

Key outputs:

- scheduler status
- integrated source freshness
- seed end / latest as-of
- post-seed realized return row count
- US/KR/BTC forward signals
- A/B/C target weights and ranking
- safety-invariant checks

## Remove schedule

```bash
sudo /bin/bash /opt/kalman/app/scripts/install_shadow_bakeoff_v1_cron.sh --remove
```

## Current seed

```text
seed_end = 2026-09-11T00:00:00+00:00
```

The seed is intentionally fixed. Do not roll it forward just to clear the
freshness gate; doing so would erase the prospective validation boundary.
