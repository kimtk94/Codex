#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
mkdir -p "$LOCK_DIR" /opt/kalman/logs

# One outer lock owns the complete US decision cycle. The market-data/model
# pipeline must commit its new strategy_signal before auto-trade evaluates it.
(
  flock -n 9 || exit 0

  echo "US_CYCLE_START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  bash "$APP_ROOT/scripts/run_pipeline.sh" US 2>&1 | tee -a /opt/kalman/logs/us.log
  echo "US_CYCLE_PIPELINE_DONE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  bash "$APP_ROOT/scripts/run_auto_trade.sh" 2>&1 | tee -a /opt/kalman/logs/auto-trade.log
  echo "US_CYCLE_DONE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
) 9>"$LOCK_DIR/us-cycle.lock"
