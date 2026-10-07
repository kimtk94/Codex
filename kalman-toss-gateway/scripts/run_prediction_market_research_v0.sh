#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 3
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ARCHIVE="${KALMAN_PM_ARCHIVE_DIR:-/home/taehoon/kalman-data/prediction-market/archive-2026-09-13}"
CANONICAL="${KALMAN_PM_CANONICAL:-/home/taehoon/kalman-data/prediction-market/canonical/prediction_macro_v0.parquet}"
OUTPUT_DIR="${KALMAN_PM_LEADLAG_DIR:-/home/taehoon/kalman-data/prediction-market/leadlag-v0}"
STRATIFIED_DIR="${KALMAN_PM_STRATIFIED_DIR:-/home/taehoon/kalman-data/prediction-market/stratified-v0}"
OOS_DIR="${KALMAN_PM_OOS_DIR:-/home/taehoon/kalman-data/prediction-market/oos-v0}"
CONFIG="${KALMAN_PM_CONFIG:-$APP_ROOT/config/prediction-market-layer-v0.json}"
OOS_SPEC="${KALMAN_PM_OOS_SPEC:-$APP_ROOT/config/prediction-market-oos-v0.json}"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] python missing: $PY" >&2
  exit 10
fi

cmd="${1:-}"
shift || true

case "$cmd" in
  archive)
    "$PY" -m research.quant_stack.prediction_market_archive_v0 \
      --archive-root "$ARCHIVE" \
      --output "$CANONICAL" \
      --config "$CONFIG" \
      "$@"
    ;;
  leadlag)
    if [ ! -f "$CANONICAL" ]; then
      echo "[FAIL] canonical prediction file missing: $CANONICAL" >&2
      exit 20
    fi
    "$PY" -m research.quant_stack.prediction_market_leadlag_v0 \
      --prediction "$CANONICAL" \
      --output-dir "$OUTPUT_DIR" \
      "$@"
    ;;
  stratified)
    if [ ! -f "$CANONICAL" ]; then
      echo "[FAIL] canonical prediction file missing: $CANONICAL" >&2
      exit 20
    fi
    "$PY" -m research.quant_stack.prediction_market_stratified_v0 \
      --prediction "$CANONICAL" \
      --output-dir "$STRATIFIED_DIR" \
      "$@"
    ;;
  oos)
    if [ ! -f "$CANONICAL" ]; then
      echo "[FAIL] canonical prediction file missing: $CANONICAL" >&2
      exit 20
    fi
    "$PY" -m research.quant_stack.prediction_market_oos_v0 \
      --prediction "$CANONICAL" \
      --spec "$OOS_SPEC" \
      --output-dir "$OOS_DIR" \
      "$@"
    ;;
  *)
    echo "Usage: $0 {archive|leadlag|stratified|oos} [args...]" >&2
    exit 2
    ;;
esac
