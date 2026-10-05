#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

# One lock owns the full cycle. Exits/reconciliation always run before a new
# entry so a due position cannot race with a fresh BUY.
(
  flock -n 9 || exit 0

  # Risk-reducing reconciliation/exit always runs first.
  "$PY" -m engine.position_manager

  # Evaluate every broker holding before a new BUY. Evaluation is read-only.
  # If it fails, keep reconciliation/audit durable but fail closed on entries.
  HOLDINGS_EVAL_OK=1
  if ! "$PY" -m engine.holdings_evaluator; then
    HOLDINGS_EVAL_OK=0
    echo "HOLDINGS_EVALUATION_FAILED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) entry=BLOCKED"
  fi

  # Keep model benchmark and broker execution audit durable before allowing
  # a new entry. If Neon/audit sync fails, the cycle stops before BUY.
  "$PY" -m engine.benchmark_ledger
  "$PY" -m engine.trade_mirror

  if [ "$HOLDINGS_EVAL_OK" -ne 1 ]; then
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

  # Capture the newly reserved/submitted entry (or no-op state) immediately.
  "$PY" -m engine.trade_mirror
) 9>"$LOCK_DIR/auto-trade.lock"
