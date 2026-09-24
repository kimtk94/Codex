#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
cd "$APP_ROOT" || exit 1
sudo env PYTHONPATH="$APP_ROOT" KALMAN_ENV_FILE="$ENV_FILE" "$PY" -m research.quant_stack.open_giveback_prospective_shadow_v3_2 "$@"
RC=$?
echo "open_giveback_shadow_v3_2_rc=$RC"
exit $RC
