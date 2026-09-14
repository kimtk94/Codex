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

## Built-in Historical Source Refresh V1

The repository now includes a conservative, fail-closed bridge that advances
the validated 2017+ integrated price-family sources from the already refreshed
Market Data V2 snapshots:

```text
research/shadow_bakeoff/historical_source_refresh.py
scripts/run_historical_source_refresh.sh
config/historical-source-refresh-v1.json
```

The refresher is intentionally narrower than the full historical collector. It
updates only validated 1D price-family indicators with direct current-source
continuity:

- US_SPY, US_QQQ, US_SOXX, US_IWM
- COMMON_GLD, COMMON_HYG, COMMON_LQD
- BTC_BTCUSD
- KR_KOSPI, KR_KOSDAQ

It does not synthesize missing FRED, liquidity, Upbit 4H, or other macro
families. Those remain subject to the existing lag / max-ffill contract.

Before appending any row, the refresher:

1. rejects incomplete same-day bars by market-session policy;
2. checks current-source close continuity against historical overlap;
3. infers the existing historical feature formula from overlap;
4. requires formula parity below the configured error threshold;
5. appends only rows strictly newer than the historical indicator max;
6. preserves the existing parquet schema;
7. writes both raw and feature parquet files through temp files;
8. creates backups before atomic replacement;
9. keeps the prospective seed unchanged.

The freshness gate now checks the feature stream of each anchor separately.
A fresh unrelated feature can no longer make `feature_ready=true` while
US_SPY, KR_KOSPI, or BTC_BTCUSD remains stale.

### First rollout

Keep cron disabled. Deploy the branch, then run:

```bash
/bin/bash /opt/kalman/app/scripts/run_historical_source_refresh.sh --dry-run
```

Review:

- source continuity error;
- selected feature formulas and parity scores;
- which rows would be appended;
- incomplete-bar filtering;
- `live_execution=false`, `toss_execution=false`,
  `neon_write=false`, `production_write=false`.

Only after the dry-run is clean:

```bash
/bin/bash /opt/kalman/app/scripts/run_historical_source_refresh.sh --apply
```

Then re-run the freshness gate / guarded bake-off manually. It is normal for a
market to remain at `WAITING_SOURCE_REFRESH` before that market's completed
daily bar exists. In particular, do not invent a US row before the US session
has completed.

After one successful manual cycle, enable the hook in `/opt/kalman/.env`:

```bash
KALMAN_SHADOW_BAKEOFF_SOURCE_REFRESH_SCRIPT=/opt/kalman/app/scripts/run_historical_source_refresh.sh
```

Do not reinstall the bake-off cron until server stability is separately
approved.

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
