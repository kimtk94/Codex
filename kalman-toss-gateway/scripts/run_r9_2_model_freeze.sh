#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
DATA_ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive}"
STATE="${R9_NEWS_STATE_DIR:-${HOME}/.local/state/kalman/r9_news_ngram}"
MENTIONS="${R9_HISTORICAL_MENTIONS:-$STATE/r9_ngram_historical.csv}"

if ! sudo test -x "$PY"; then
  echo "ERROR: protected Python missing/not executable as root: $PY" >&2
  exit 20
fi
if [[ ! -s "$MENTIONS" ]]; then
  echo "ERROR: historical R9 mentions missing: $MENTIONS" >&2
  exit 21
fi

ARGS=()
if [[ "${R9_2_FREEZE_MODEL:-NO}" != "YES" ]]; then
  ARGS+=(--verify-only)
fi

echo "===== R9.2 MODEL FREEZE / VERIFY ====="
echo "data_root=$DATA_ROOT"
echo "mentions=$MENTIONS"
echo "production_changed=false"

sudo env \
  PYTHONPATH="$ROOT/research:$ROOT" \
  KALMAN_DATA_ROOT="$DATA_ROOT" \
  R9_NEWS_STATE_DIR="$STATE" \
  R9_2_FREEZE_MODEL="${R9_2_FREEZE_MODEL:-NO}" \
  R9_2_FREEZE_CONFIRM="${R9_2_FREEZE_CONFIRM:-}" \
  "$PY" "$ROOT/research/r9_2_model_freeze.py" \
    --root "$DATA_ROOT" \
    --mentions "$MENTIONS" \
    "${ARGS[@]}"

echo
echo "R9_2_MODEL_FREEZE_STAGE=PASS"
