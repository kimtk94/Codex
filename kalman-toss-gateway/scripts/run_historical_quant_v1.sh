#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="${VENV}/bin/python"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

[ -x "$PY" ] || { echo "[FAIL] Research V2 Python missing: $PY" >&2; exit 10; }
mkdir -p "$LOCK_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values
p = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
v = dotenv_values(p) if p.exists() else {}
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

case "$DATA_ROOT" in
  "$GDRIVE_MOUNT"|"$GDRIVE_MOUNT"/*)
    mountpoint -q "$GDRIVE_MOUNT" || { echo "[FAIL] Google Drive mount unavailable" >&2; exit 20; }
    timeout 20 ls "$GDRIVE_MOUNT" >/dev/null || { echo "[FAIL] Google Drive unreadable" >&2; exit 21; }
    ;;
esac

SPEC="${KALMAN_MODEL_V2_SPEC:-$APP_ROOT/config/model-v2-spec.json}"
ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
MATRIX_DIR="${KALMAN_MODEL_V2_MATRIX_DIR:-$ROOT/matrices}"
OUTPUT_DIR="${KALMAN_HISTORICAL_QUANT_ROOT:-$ROOT/historical_quant_v1}"

TRAIN="${KALMAN_WF_TRAIN:-504}"
VALID="${KALMAN_WF_VALID:-63}"
TEST="${KALMAN_WF_TEST:-126}"
MAX_HOLD="${KALMAN_WF_MAX_HOLD_BARS:-20}"
START_DATE="${KALMAN_WF_START_DATE:-2017-01-01}"
QLIB_ENABLED="${KALMAN_QLIB_ENABLED:-false}"
QLIB_TRACKING_ROOT="${KALMAN_QLIB_TRACKING_ROOT:-$LOCK_DIR/qlib_mlruns}"
QLIB_PROVIDER_ROOT="${KALMAN_QLIB_PROVIDER_ROOT:-$LOCK_DIR/qlib_provider}"
QLIB_EXPERIMENT_NAME="${KALMAN_QLIB_EXPERIMENT_NAME:-kalman_historical_quant_v1}"
PORTFOLIO_ENABLED="${KALMAN_PORTFOLIO_ENABLED:-true}"
PORTFOLIO_METHOD="${KALMAN_PORTFOLIO_METHOD:-hrp}"
PORTFOLIO_LOOKBACK_DAYS="${KALMAN_PORTFOLIO_LOOKBACK_DAYS:-180}"
PORTFOLIO_MIN_OBSERVATIONS="${KALMAN_PORTFOLIO_MIN_OBSERVATIONS:-90}"
PORTFOLIO_REBALANCE="${KALMAN_PORTFOLIO_REBALANCE:-M}"
LEAN_EXECUTION_ENABLED="${KALMAN_LEAN_EXECUTION_ENABLED:-true}"
LEAN_EXECUTION_MAX_SYMBOL_WEIGHT="${KALMAN_LEAN_EXECUTION_MAX_SYMBOL_WEIGHT:-0.75}"
LEAN_EXECUTION_MAX_GROSS_WEIGHT="${KALMAN_LEAN_EXECUTION_MAX_GROSS_WEIGHT:-1.0}"
LEAN_EXECUTION_MIN_ORDER_NOTIONAL="${KALMAN_LEAN_EXECUTION_MIN_ORDER_NOTIONAL:-10}"
LEAN_EXECUTION_MAX_SINGLE_ORDER_FRACTION="${KALMAN_LEAN_EXECUTION_MAX_SINGLE_ORDER_FRACTION:-0.80}"
LEAN_EXECUTION_MAX_TOTAL_TURNOVER_FRACTION="${KALMAN_LEAN_EXECUTION_MAX_TOTAL_TURNOVER_FRACTION:-2.0}"
RISKFOLIO_ENABLED="${KALMAN_RISKFOLIO_ENABLED:-auto}"
RISKFOLIO_VENV="${KALMAN_RISKFOLIO_VENV:-/opt/kalman/.venv-riskfolio}"
RISKFOLIO_PY="${RISKFOLIO_VENV}/bin/python"
RISKFOLIO_LOOKBACK_DAYS="${KALMAN_RISKFOLIO_LOOKBACK_DAYS:-180}"
RISKFOLIO_MIN_OBSERVATIONS="${KALMAN_RISKFOLIO_MIN_OBSERVATIONS:-90}"
RISKFOLIO_REBALANCE="${KALMAN_RISKFOLIO_REBALANCE:-M}"

cd "$APP_ROOT"
exec 9>"$LOCK_DIR/historical-quant-v1.lock"
flock -n 9 || { echo "HISTORICAL_QUANT_V1_ALREADY_RUNNING" >&2; exit 30; }

GIT_SHA="${KALMAN_GIT_SHA:-}"
if [ -z "$GIT_SHA" ] && command -v git >/dev/null 2>&1; then
  GIT_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
fi

ARGS=(
  -m research.quant_stack.experiment_runner
  --matrix-dir "$MATRIX_DIR"
  --spec "$SPEC"
  --output-dir "$OUTPUT_DIR"
  --start-date "$START_DATE"
  --train "$TRAIN"
  --valid "$VALID"
  --test "$TEST"
  --max-hold-bars "$MAX_HOLD"
)

if [ -n "$GIT_SHA" ]; then
  ARGS+=(--git-sha "$GIT_SHA")
fi

if [ "${PORTFOLIO_ENABLED,,}" = "true" ]; then
  "$PY" -c 'import pypfopt' >/dev/null 2>&1 || {
    echo "[FAIL] PyPortfolioOpt missing. Install research/quant_stack/requirements-pypfopt.txt" >&2
    exit 11
  }
  ARGS+=(
    --portfolio-targets
    --portfolio-method "$PORTFOLIO_METHOD"
    --portfolio-lookback-days "$PORTFOLIO_LOOKBACK_DAYS"
    --portfolio-min-observations "$PORTFOLIO_MIN_OBSERVATIONS"
    --portfolio-rebalance "$PORTFOLIO_REBALANCE"
  )
fi

if [ "${QLIB_ENABLED,,}" = "true" ]; then
  ARGS+=(
    --qlib-recorder
    --qlib-tracking-root "$QLIB_TRACKING_ROOT"
    --qlib-provider-root "$QLIB_PROVIDER_ROOT"
    --qlib-experiment-name "$QLIB_EXPERIMENT_NAME"
  )
fi

"$PY" "${ARGS[@]}"

"$PY" -m research.quant_stack.validate_artifacts --output-dir "$OUTPUT_DIR"

LEAN_EXECUTION_RAN=false
if [ "${LEAN_EXECUTION_ENABLED,,}" = "true" ] && [ "${PORTFOLIO_ENABLED,,}" = "true" ]; then
  "$PY" -m research.quant_stack.lean_execution_runner \
    --output-dir "$OUTPUT_DIR" \
    --max-symbol-weight "$LEAN_EXECUTION_MAX_SYMBOL_WEIGHT" \
    --max-gross-weight "$LEAN_EXECUTION_MAX_GROSS_WEIGHT" \
    --min-order-notional "$LEAN_EXECUTION_MIN_ORDER_NOTIONAL" \
    --max-single-order-fraction "$LEAN_EXECUTION_MAX_SINGLE_ORDER_FRACTION" \
    --max-total-turnover-fraction "$LEAN_EXECUTION_MAX_TOTAL_TURNOVER_FRACTION"
  LEAN_EXECUTION_RAN=true
elif [ "${LEAN_EXECUTION_ENABLED,,}" = "true" ]; then
  echo "LEAN_EXECUTION_CONTRACT_SKIPPED portfolio layer disabled"
fi

RISKFOLIO_RAN=false
if [ "${RISKFOLIO_ENABLED,,}" = "true" ]; then
  [ -x "$RISKFOLIO_PY" ] || {
    echo "[FAIL] Riskfolio Python missing: $RISKFOLIO_PY" >&2
    exit 12
  }
  "$RISKFOLIO_PY" -c 'import riskfolio' >/dev/null 2>&1 || {
    echo "[FAIL] riskfolio-lib missing in $RISKFOLIO_VENV" >&2
    exit 13
  }
  "$RISKFOLIO_PY" -m research.quant_stack.riskfolio_benchmark_runner \
    --output-dir "$OUTPUT_DIR" \
    --lookback-days "$RISKFOLIO_LOOKBACK_DAYS" \
    --min-observations "$RISKFOLIO_MIN_OBSERVATIONS" \
    --rebalance "$RISKFOLIO_REBALANCE"
  RISKFOLIO_RAN=true
elif [ "${RISKFOLIO_ENABLED,,}" = "auto" ]; then
  if [ -x "$RISKFOLIO_PY" ] && "$RISKFOLIO_PY" -c 'import riskfolio' >/dev/null 2>&1; then
    "$RISKFOLIO_PY" -m research.quant_stack.riskfolio_benchmark_runner \
      --output-dir "$OUTPUT_DIR" \
      --lookback-days "$RISKFOLIO_LOOKBACK_DAYS" \
      --min-observations "$RISKFOLIO_MIN_OBSERVATIONS" \
      --rebalance "$RISKFOLIO_REBALANCE"
    RISKFOLIO_RAN=true
  else
    echo "RISKFOLIO_BENCHMARK_SKIPPED isolated venv not ready"
  fi
fi

printf 'HISTORICAL_QUANT_V1_COMPLETE root=%s start=%s validation=READY qlib=%s portfolio=%s method=%s lean_execution=%s riskfolio=%s\n' \
  "$OUTPUT_DIR" "$START_DATE" "$QLIB_ENABLED" "$PORTFOLIO_ENABLED" "$PORTFOLIO_METHOD" "$LEAN_EXECUTION_RAN" "$RISKFOLIO_RAN"
