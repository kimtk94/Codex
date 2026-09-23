#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE="${R9_NEWS_STATE_DIR:-${HOME}/.local/state/kalman/r9_news_ngram}"
DATA_ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive}"
MENTIONS="${R9_NGRAM_MENTIONS:-$STATE/r9_ngram_historical.csv}"
MANIFEST="${R9_NGRAM_MANIFEST:-$STATE/manifest.json}"
BOOTSTRAP="${R9_1_BOOTSTRAP:-2000}"

if [[ "${R9_1_EXECUTE:-NO}" != "YES" ]]; then
  echo "R9.1 is preregistered but execution is guarded."
  echo "Set R9_1_EXECUTE=YES to run the single frozen ablation."
  exit 0
fi

if ! sudo test -x "$PY"; then
  echo "ERROR: protected Python missing or not executable as root: $PY" >&2
  exit 20
fi
[[ -s "$MENTIONS" ]] || { echo "ERROR: mentions missing/empty: $MENTIONS" >&2; exit 21; }
[[ -s "$MANIFEST" ]] || { echo "ERROR: manifest missing/empty: $MANIFEST" >&2; exit 22; }

echo "===== R9.1 SINGLE PREREGISTERED NGRAM ABLATION ====="
echo "data_root=$DATA_ROOT"
echo "mentions=$MENTIONS"
echo "manifest=$MANIFEST"
echo "bootstrap=$BOOTSTRAP"
echo "production_changed=false"
echo "live_action=NONE"

sudo env \
  PYTHONPATH="$ROOT/research:$ROOT" \
  KALMAN_DATA_ROOT="$DATA_ROOT" \
  R9_NEWS_STATE_DIR="$STATE" \
  R9_ALLOW_LIVE=false \
  "$PY" "$ROOT/research/r9_1_ngram_ablation.py" \
    --root "$DATA_ROOT" \
    --mentions "$MENTIONS" \
    --news-manifest "$MANIFEST" \
    --bootstrap "$BOOTSTRAP"

echo
echo "R9_1_ABLATION=PASS"
