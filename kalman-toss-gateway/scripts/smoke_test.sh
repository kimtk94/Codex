#!/usr/bin/env bash
set -euo pipefail
BASE="${KALMAN_BASE:-/opt/kalman}"
APP_ROOT="${KALMAN_APP_ROOT:-$BASE/app}"
ENV_FILE="${KALMAN_ENV_FILE:-$BASE/.env}"
PY="${KALMAN_PYTHON:-$BASE/.venv/bin/python}"
RUN_PIPELINES=false
[ "${1:-}" = "--pipelines" ] && RUN_PIPELINES=true

export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"

"$APP_ROOT/scripts/preflight.sh"

if [ "$(id -u)" -eq 0 ]; then
  systemctl restart kalman-toss-gateway
  sleep 2
fi

printf '\n== Gateway health ==\n'
curl -fsS "http://127.0.0.1:8787/health"; printf '\n'

read_env(){
  "$PY" - "$1" <<'PY'
import os, sys
from dotenv import dotenv_values
v=dotenv_values(os.environ['KALMAN_ENV_FILE'])
print(v.get(sys.argv[1]) or '')
PY
}

SECRET="$(read_env HUB_GATEWAY_SECRET)"
TOSS_ID="$(read_env TOSS_CLIENT_ID)"
TOSS_SECRET="$(read_env TOSS_CLIENT_SECRET)"
ACCOUNT="$(read_env TOSS_ACCOUNT)"

if [ -n "$SECRET" ]; then
  printf '\n== Gateway auth / risk-only probe ==\n'
  curl -fsS -X POST "http://127.0.0.1:8787/api/order-probe" \
    -H 'Content-Type: application/json' \
    -H "X-Gateway-Secret: $SECRET" \
    -d '{"symbol":"IONQ","amount_krw":1000}'; printf '\n'
else
  printf '[WARN] HUB_GATEWAY_SECRET missing; protected route test skipped.\n'
fi

if [ -n "$SECRET" ] && [ -n "$TOSS_ID" ] && [ -n "$TOSS_SECRET" ]; then
  printf '\n== Toss read-only account discovery ==\n'
  curl -fsS "http://127.0.0.1:8787/api/accounts" -H "X-Gateway-Secret: $SECRET"; printf '\n'
  if [ -n "$ACCOUNT" ]; then
    printf '\n== Toss read-only holdings ==\n'
    curl -fsS "http://127.0.0.1:8787/api/holdings" -H "X-Gateway-Secret: $SECRET"; printf '\n'
    printf '\n== Toss read-only buying power (USD) ==\n'
    curl -fsS "http://127.0.0.1:8787/api/buying-power?currency=USD" -H "X-Gateway-Secret: $SECRET"; printf '\n'
  else
    printf '[WARN] TOSS_ACCOUNT is empty; holdings/buying-power tests skipped until accountSeq is configured.\n'
  fi
else
  printf '[WARN] Toss OAuth credentials incomplete; Toss upstream tests skipped.\n'
fi

if $RUN_PIPELINES; then
  printf '\n== KR_GLOBAL ==\n'
  "$APP_ROOT/scripts/run_pipeline.sh" KR_GLOBAL
  printf '\n== US ==\n'
  "$APP_ROOT/scripts/run_pipeline.sh" US
  printf '\n== CRYPTO_GLOBAL ==\n'
  "$APP_ROOT/scripts/run_pipeline.sh" CRYPTO_GLOBAL
  mkdir -p "$BASE/state"
  date -u +'%Y-%m-%dT%H:%M:%SZ' > "$BASE/state/smoke.ok"
  printf '[PASS] Full pipeline smoke test passed; stamp written to %s/state/smoke.ok\n' "$BASE"
else
  printf '\n[PASS] Read-only smoke test passed. Run with --pipelines before installing cron.\n'
fi
