# Kalman Forward SHADOW Bake-off V1 — Server Runbook

## Purpose

Track three portfolio allocators on new forward data without enabling live trading.

- A: Hybrid + Equal Weight
- B: Hybrid + Static Max Sharpe
- C: Hybrid + risk_cap_110
- Hybrid sleeves: US V2 / KR V3 / BTC V2

The server path is file-only and fail-closed.

## Safety invariants

The automation must preserve:

- production_write=false
- neon_write=false
- toss_execution=false
- live_execution=false
- auto_trade_visible=false
- dashboard_snapshot_created=false

The daily runner refuses to run if:

- TRADING_ENABLED=true
- LIVE_TRADING_CONFIRM is set

## Important source constraint

The current V2 scheduled refresh updates:

1. Market Data V2
2. TA-Lib Features V2
3. fixed-model V2 SHADOW

It does **not** rewrite the historical integrated lineage used by the V2/V3 historical champions:

- Market_Data/v2/raw/historical_2017/multimarket_raw_2017_present.parquet
- Market_Features/v2/talib/historical_2017/multimarket_features_2017_present_v0_3.parquet

Therefore the new daily orchestrator includes a source freshness gate.

If the three historical anchors and integrated feature file have not advanced beyond the frozen seed:

- seed_end = 2026-09-11T00:00:00Z

the job writes:

- Market_Model_V2/shadow_bakeoff/v1/latest/source_freshness.json

with:

- status=WAITING_SOURCE_REFRESH

and exits successfully without fabricating forward PnL.

## Files

- research/shadow_bakeoff/source_freshness.py
- research/shadow_bakeoff/forward_scorer.py
- research/shadow_bakeoff/runner.py
- scripts/run_shadow_bakeoff_v1.sh
- scripts/run_shadow_bakeoff_daily.sh
- scripts/install_shadow_bakeoff_v1_cron.sh
- config/shadow-bakeoff-v1.cron.example

## Manual smoke

From the deployed server repository:

```bash
cd /opt/kalman/app
/bin/bash scripts/run_shadow_bakeoff_daily.sh
```

Expected current result while the historical integrated source is still frozen:

```text
SHADOW_BAKEOFF_WAITING_SOURCE_REFRESH
```

This is a normal safe state.

## Install cron

```bash
sudo /bin/bash /opt/kalman/app/scripts/install_shadow_bakeoff_v1_cron.sh --install
```

Installed schedule:

```text
CRON_TZ=Asia/Seoul
10 8 * * 2-6 root /bin/bash /opt/kalman/app/scripts/run_shadow_bakeoff_daily.sh >> /opt/kalman/logs/shadow-bakeoff-v1.log 2>&1
```

Rationale:

- Tue-Sat 08:10 KST
- after the prior US close
- before the KR regular session
- avoids presenting intraday KR data as a completed daily anchor

## Inspect installation

```bash
sudo /bin/bash /opt/kalman/app/scripts/install_shadow_bakeoff_v1_cron.sh --show
```

## Remove cron

```bash
sudo /bin/bash /opt/kalman/app/scripts/install_shadow_bakeoff_v1_cron.sh --remove
```

## Status

Source freshness:

```bash
cat /mnt/gdrive/Market_Model_V2/shadow_bakeoff/v1/latest/source_freshness.json
```

Bake-off:

```bash
cat /mnt/gdrive/Market_Model_V2/shadow_bakeoff/v1/latest/bakeoff_status.json
```

Log:

```bash
tail -n 200 /opt/kalman/logs/shadow-bakeoff-v1.log
```

## Promotion policy

The cron itself never promotes anything.

State progression remains:

```text
RESEARCH
  -> BACKTEST_PASS
  -> SHADOW
  -> PAPER
  -> LIVE_CANDIDATE
  -> LIVE
```

A/B/C forward results are observational evidence only until a separate promotion decision is explicitly approved.
