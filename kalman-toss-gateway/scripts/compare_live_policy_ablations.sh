#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"

export KALMAN_ENV_FILE="$ENV_FILE"

echo "===================================================="
echo "DIRECT PROFIT-FLIP ABLATION COMPARISON"
echo "===================================================="
echo "app_root=$APP_ROOT"

cd "$APP_ROOT"
CD_RC=$?
if [[ $CD_RC -ne 0 ]]; then
  echo "[FAIL] cannot cd to app_root=$APP_ROOT rc=$CD_RC"
  exit "$CD_RC"
fi

"$PY" -m research.quant_stack.compare_live_policy_ablations "$@"
RC=$?

echo
echo "===== COMPARISON RESULT ====="
echo "rc=$RC"
echo "No production, order, cron, or managed-position writes were performed."

exit "$RC"
