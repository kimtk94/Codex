# Kalman V2 SHADOW Stack Runbook

This runbook covers the manual end-to-end V2 research/shadow flow.

## Flow

```text
Market Data V2
  -> TA-Lib Features V2
  -> Finviz point-in-time snapshot
  -> Model V2 retrain
  -> file-only SHADOW signal
  -> Neon SHADOW validation
  -> optional Neon SHADOW mirror
```

The execution gateway and Toss order path are not part of this stack.

## Safety invariants

Before the stack starts, it requires:

- `TRADING_ENABLED` is not `true`
- `LIVE_TRADING_CONFIRM` is empty
- Market V2 and Research V2 environments are isolated from production
- Google Drive is mounted/readable when `KALMAN_DATA_ROOT` is under `/mnt/gdrive`

The Neon writer itself also enforces:

- signal remains `SHADOW`
- `entry_allowed=false`
- `payload.allow_trade_shadow=false`
- `payload.live_execution=false`
- `payload.production_promotion=false`
- no `dashboard_snapshot`
- `pipeline_run.status=ABORTED`
- no visibility through the existing auto-trade join
- `v_latest_successful_run` remains unchanged

## First manual run

Install missing isolated V2 environments if necessary:

```bash
sudo /opt/kalman/app/scripts/run_v2_shadow_stack.sh --install-missing
```

This runs the full file-based stack and performs Neon validation only. No Neon write occurs.

## One-time Neon SHADOW mirror

After the dry-run completes successfully:

```bash
sudo /opt/kalman/app/scripts/run_v2_shadow_stack.sh \
  --install-missing \
  --mirror-neon
```

The runner creates a protected temporary copy of `/opt/kalman/.env`, enables only the two Neon shadow gates in that temporary file, performs the mirror, and securely deletes the temporary file afterward.

The canonical `/opt/kalman/.env` remains unchanged.

## Finviz

Manual stack runs call Finviz with `--force` to create a point-in-time snapshot even when the default environment setting is disabled.

Finviz is treated as best-effort in this stack because the current Model V2 pipeline does not consume it directly. If Finviz is blocked or rate-limited, the runner records the failure and continues with Model V2.

To skip it intentionally:

```bash
sudo /opt/kalman/app/scripts/run_v2_shadow_stack.sh --skip-finviz
```

## Main outputs

Using the default Google Drive-backed configuration:

```text
/mnt/gdrive/Market_Data/v2/
/mnt/gdrive/Market_Features/v2/
/mnt/gdrive/Market_Screeners/finviz/
/mnt/gdrive/Market_Model_V2/
```

Key files:

```text
Market_Data/v2/market_data_v2_run_status.json
Market_Features/v2/features_v2_run_status.json
Market_Screeners/finviz/finviz_run_status.json
Market_Model_V2/shadow/latest/shadow_signals.json
Market_Model_V2/shadow/neon_mirror_status.json
```

## Cron policy

Do not add this runner to cron until manual runs show stable data coverage, stable Model V2 outputs, and a successful Neon SHADOW transaction invariant check.

Model V2 retraining remains manual by design. A later scheduled path should normally use fixed-model SHADOW scoring rather than retraining on every cycle.


## Scheduled fixed-model SHADOW operation

Retraining remains manual. Production scheduling uses only the existing JSON model artifacts:

```text
Market Data V2
  -> TA-Lib Features V2
  -> optional Finviz PIT
  -> run_shadow_v2.sh (fixed model; no retrain)
  -> Neon SHADOW mirror
```

KST schedule:

- Monday-Friday 16:50: KR close refresh, `--skip-finviz`
- Tuesday-Saturday 07:30: US close refresh, Finviz included

Both runs also refresh BTC/common inputs and score all three V2 markets (US/KR/BTC).

The scheduled runner refuses to operate when `TRADING_ENABLED=true` or when `LIVE_TRADING_CONFIRM` is set. It additionally requires Market Data and TA-Lib feature status to be exactly `READY` before scoring.

The scheduled path never calls `run_model_v2_research.sh`.
