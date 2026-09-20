#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"

export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$APP_ROOT"

cmd="${1:-status}"
shift || true

case "$cmd" in
  sync)
    "$PY" -m engine.benchmark_ledger
    "$PY" -m engine.macro_shadow_eval_v1 sync "$@"
    ;;
  status|selftest)
    "$PY" -m engine.macro_shadow_eval_v1 "$cmd" "$@"
    ;;
  *)
    echo "usage: $0 {sync|status|selftest}" >&2
    exit 2
    ;;
esac
