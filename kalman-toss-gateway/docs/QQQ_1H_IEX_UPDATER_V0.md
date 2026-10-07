# QQQ 1h Alpaca IEX Updater v0

Date: 2026-10-07 KST

## Purpose

Keep the research-only QQQ 1-hour canonical history current for the frozen
prediction-market OOS experiment without changing the live trading engine.

Canonical file:

`/home/taehoon/kalman-data/market/1h/QQQ_1h_2017plus.parquet`

Google Drive mirror:

`gdrive:US_ETF/history_1h/QQQ_1h_2017plus.parquet`

## Frozen data contract

The updater uses:

- symbol: QQQ
- provider: Alpaca Market Data
- timeframe: 1Hour
- feed: IEX
- adjustment: raw
- schema/order: `c,h,l,n,o,t,v,vw`

The current canonical already uses the native Alpaca bar field layout. Existing
Kalman IEX research code also uses `feed=iex` and `adjustment=raw`. Because the
historical generator was not separately recoverable from Git history, the
updater does not trust this inference by itself. Every run re-fetches a five-day
overlap and requires all shared OHLC/VWAP/volume/trade-count values to match
exactly (prices within 1e-9 absolute tolerance) before any append is allowed.

A mismatch is treated as possible feed/adjustment drift or upstream data
revision and causes `ERROR_FAIL_CLOSED`.

## Write policy

The updater:

1. reads the existing canonical exactly as-is;
2. fetches a five-day overlap plus new Alpaca IEX 1-hour bars;
3. drops the currently incomplete UTC hour;
4. validates overlap;
5. appends only rows with `t > existing_max_timestamp`;
6. verifies the existing prefix did not change;
7. creates a local versioned backup;
8. atomically replaces the local parquet;
9. creates a versioned Google Drive backup;
10. uploads the new canonical;
11. downloads it again and verifies SHA256;
12. restores the Drive backup if upload/verification fails.

No historical row is recomputed or overwritten.

## Security model

The protected `/opt/kalman/.env` is never copied into the user's research
directory. The deployed updater is a root-owned code snapshot under:

`/opt/kalman/qqq-updater-v0`

It has its own root-owned Python venv and reads the existing Kalman
`EnvironmentFile=/opt/kalman/.env` through systemd. It does not modify the
live gateway service or the live gateway Python environment.

Local parquet/status ownership is restored to the canonical file's existing
owner after a root-run update.

## Timer

The systemd timer is configured for every hour at minute 07:

`OnCalendar=*-*-* *:07:00`

The prediction-market OOS watcher runs later at minute 17 on its six-hour
schedule, so a newly appended QQQ canonical can be mirrored before OOS
evaluation.

## Installation

Installation requires one interactive sudo authorization because the current
remote session intentionally does not have passwordless sudo.

Run from the branch worktree:

```bash
cd /home/taehoon/Codex-PREDICTION-MARKET-20261007/kalman-toss-gateway
bash scripts/install_qqq_1h_iex_updater_v0.sh
```

The installer first deploys the root-owned snapshot and isolated venv, then
runs the updater one time. The timer is enabled only if that first real
credential/API/overlap validation succeeds.

## Current pre-install validation

Normal-user execution on 2026-10-07 produced the expected fail-closed state
because Alpaca credentials are protected from the user session:

- status: `ERROR_FAIL_CLOSED`
- reason: Alpaca credentials missing
- canonical before SHA256:
  `a981f129635517a2df68a63d233ae693081f66f5539e31da9aa05a4df605cfcf`
- canonical after SHA256:
  `a981f129635517a2df68a63d233ae693081f66f5539e31da9aa05a4df605cfcf`
- canonical changed: no

This is the intended behavior before the systemd EnvironmentFile is available.

### rclone credential isolation

The installer copies the working user rclone configuration into
`/opt/kalman/qqq-updater-v0/rclone.conf`, owned by root with mode 0600.
The root service uses only that deployed copy. This prevents token refreshes
from changing the ownership or contents of
`/home/taehoon/.config/rclone/rclone.conf`.
