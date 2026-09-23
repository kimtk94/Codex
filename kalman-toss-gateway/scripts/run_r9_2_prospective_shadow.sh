#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
DATA_ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive}"
STATE="${R9_NEWS_STATE_DIR:-${HOME}/.local/state/kalman/r9_news_ngram}"
NEWS_HISTORY="${R9_SHADOW_HISTORY:-$STATE/r9_ngram_shadow_history.csv}"
SOURCE_STATE="${R9_SHADOW_SOURCE_STATE:-$STATE/r9_shadow_source_state.json}"

if [[ "${R9_2_SHADOW_EXECUTE:-NO}" != "YES" ]]; then
  echo "REFUSED: set R9_2_SHADOW_EXECUTE=YES to run the research-only shadow scorer." >&2
  exit 20
fi
if ! sudo test -x "$PY"; then
  echo "ERROR: protected Python missing/not executable as root: $PY" >&2
  exit 21
fi
if [[ ! -s "$NEWS_HISTORY" || ! -s "$SOURCE_STATE" ]]; then
  echo "ERROR: R9.2 NGram shadow history/source state not ready." >&2
  echo "Run scripts/run_r9_2_ngram_incremental.sh first." >&2
  exit 22
fi

ARGS=()
if [[ "${R9_2_NEON_WRITE:-NO}" == "YES" ]]; then
  ARGS+=(--write-neon)
fi

echo "===== R9.2 FORWARD-ONLY SHADOW ====="
echo "data_root=$DATA_ROOT"
echo "news_history=$NEWS_HISTORY"
echo "source_state=$SOURCE_STATE"
echo "production_changed=false"
echo "broker_execution=false"

sudo env \
  PYTHONPATH="$ROOT/research:$ROOT" \
  KALMAN_DATA_ROOT="$DATA_ROOT" \
  R9_NEWS_STATE_DIR="$STATE" \
  KALMAN_ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}" \
  KALMAN_R9_2_SHADOW_NEON_ENABLED="${KALMAN_R9_2_SHADOW_NEON_ENABLED:-false}" \
  KALMAN_R9_2_SHADOW_NEON_CONFIRM="${KALMAN_R9_2_SHADOW_NEON_CONFIRM:-}" \
  "$PY" "$ROOT/research/r9_2_prospective_shadow.py" \
    --root "$DATA_ROOT" \
    --news-history "$NEWS_HISTORY" \
    --source-state "$SOURCE_STATE" \
    "${ARGS[@]}"

echo
echo "R9_2_SHADOW_STAGE=PASS"
