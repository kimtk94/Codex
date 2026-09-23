#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
DATA_ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive}"
STATE="${R9_NEWS_STATE_DIR:-${HOME}/.local/state/kalman/r9_news_ngram}"
NEWS_HISTORY="${R9_SHADOW_HISTORY:-$STATE/r9_ngram_shadow_history.csv}"
SOURCE_STATE="${R9_SHADOW_SOURCE_STATE:-$STATE/r9_shadow_source_state.json}"

if [[ "${R9_2_PREBOUNDARY_DIAGNOSTIC:-NO}" != "YES" ]]; then
  echo "REFUSED: set R9_2_PREBOUNDARY_DIAGNOSTIC=YES." >&2
  exit 20
fi

if ! sudo test -x "$PY"; then
  echo "ERROR: protected Python missing/not executable as root: $PY" >&2
  exit 21
fi

if [[ ! -s "$NEWS_HISTORY" || ! -s "$SOURCE_STATE" ]]; then
  echo "ERROR: R9.2 NGram history/source state missing." >&2
  exit 22
fi

echo "===== R9.2 PRE-BOUNDARY DIAGNOSTIC ====="
echo "window=2026-09-23T13:30:00Z..2026-09-24T13:30:00Z"
echo "required_news_day=2026-09-22"
echo "prospective_evidence=false"
echo "trade_entry=false"
echo "outcome=false"
echo "neon_write=false"
echo "strategy_signal_write=false"
echo "live_execution=false"
echo "production_changed=false"

sudo env   PYTHONPATH="$ROOT/research:$ROOT"   KALMAN_DATA_ROOT="$DATA_ROOT"   R9_NEWS_STATE_DIR="$STATE"   "$PY" "$ROOT/research/r9_2_preboundary_diagnostic.py"     --root "$DATA_ROOT"     --news-history "$NEWS_HISTORY"     --source-state "$SOURCE_STATE"

echo
echo "R9_2_PREBOUNDARY_STAGE=PASS"
