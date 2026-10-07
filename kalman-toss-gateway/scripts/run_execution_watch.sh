#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

# Risk exits must remain live even while the hourly US model pipeline owns
# us-cycle.lock. Entries, however, must never evaluate a previous signal while
# that refresh is in flight.
(
  if ! flock -n 8; then
    echo "EXECUTION_WATCH_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=AUTO_TRADE_LOCK_BUSY"
    exit 0
  fi

  echo "EXECUTION_WATCH_START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # Always reconcile positions first so stop-loss, take-profit,
  # profit-flip, max-hold and Friday-flat remain protected.
  "$PY" -m engine.position_manager

  HOLDINGS_EVAL_OK=1
  HOLDINGS_REVIEW_BLOCK=0
  if ! "$PY" -m engine.holdings_evaluator; then
    HOLDINGS_EVAL_OK=0
    echo "HOLDINGS_EVALUATION_FAILED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) entry=BLOCKED"
  else
    STRONG_SELL_REVIEW_COUNT="$("$PY" - <<'PY'
import json
from pathlib import Path
p=Path("/opt/kalman/state/holdings-evaluation-latest.json")
j=json.loads(p.read_text(encoding="utf-8"))
print(int((j.get("summary") or {}).get("strong_sell_review_count") or 0))
PY
)"
    if [ "$STRONG_SELL_REVIEW_COUNT" -gt 0 ]; then
      HOLDINGS_REVIEW_BLOCK=1
      echo "HOLDINGS_STRONG_SELL_REVIEW_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) count=$STRONG_SELL_REVIEW_COUNT entry=BLOCKED"
    fi
  fi

  "$PY" -m engine.trade_mirror
  if ! "$PY" -m engine.execution_cost_calibrator; then
    echo "EXECUTION_COST_CALIBRATION_WARN_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  fi

  # Research-only early-session observer. It records hypothetical 5K + 5K
  # OPEN_CARRY entries and never submits broker orders. Failure here must not
  # interfere with the existing hourly LIVE path.
  if ! "$PY" -m engine.open_carry_shadow; then
    echo "OPEN_CARRY_SHADOW_ERROR_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  fi

  if [ "$HOLDINGS_EVAL_OK" -ne 1 ]; then
    echo "EXECUTION_ENTRY_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=HOLDINGS_EVALUATION_FAILED risk_manager=COMPLETED"
    exit 0
  fi
  if [ "$HOLDINGS_REVIEW_BLOCK" -eq 1 ]; then
    echo "EXECUTION_ENTRY_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=HOLDINGS_STRONG_SELL_REVIEW risk_manager=COMPLETED"
    exit 0
  fi

  # Only the entry stage needs the model-cycle lock. If the hourly model
  # refresh is still running, skip entries but keep risk management complete.
  (
    if ! flock -n 9; then
      echo "EXECUTION_ENTRY_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=US_CYCLE_LOCK_BUSY risk_manager=COMPLETED"
      exit 0
    fi

    # Guarded early-session carry entry. The module is fail-closed and only
    # submits when OPEN_CARRY_LIVE_ENABLED=true plus its explicit confirmation
    # token and 5K x 2 contract are all present.
    if ! "$PY" -m engine.open_carry_live; then
      echo "OPEN_CARRY_LIVE_ERROR_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) entry=BLOCKED"
      exit 0
    fi

    POLICY="$("$PY" - <<'PY'
import os
from dotenv import dotenv_values
v = dotenv_values(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
print((v.get("AUTO_TRADE_SIGNAL_POLICY") or "").strip().upper())
PY
)"

    if [ "$POLICY" = "R5_LIVE_CONDITIONAL" ]; then
      "$PY" -m engine.r5_conditional_live
    else
      "$PY" -m engine.auto_trade
    fi

    "$PY" -m engine.trade_mirror
  ) 9>"$LOCK_DIR/us-cycle.lock"

  echo "EXECUTION_WATCH_DONE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
) 8>"$LOCK_DIR/auto-trade.lock"
