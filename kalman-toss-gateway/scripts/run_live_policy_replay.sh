#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$LOCAL_APP_ROOT}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"

export KALMAN_ENV_FILE="$ENV_FILE"

if [[ ! -f "$APP_ROOT/research/quant_stack/live_policy_replay.py" ]]; then
  echo "LIVE_POLICY_REPLAY_MODULE_MISSING app_root=$APP_ROOT" >&2
  exit 2
fi

cd "$APP_ROOT" || {
  echo "[FAIL] cannot cd to app_root=$APP_ROOT" >&2
  exit 2
}

"$PY" -m research.quant_stack.live_policy_replay "$@"
RC=$?

if [[ $RC -ne 0 ]]; then
  echo "[FAIL] live policy replay rc=$RC" >&2
else
  echo "[PASS] live policy replay rc=0"
fi

exit "$RC"
