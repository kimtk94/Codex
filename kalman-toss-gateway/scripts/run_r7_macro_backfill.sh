#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
MODE="${1:-smoke}"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export KALMAN_ENV_FILE="$ENV_FILE"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }
[ -f "$APP_ROOT/research/r7_macro_backfill.py" ] || { echo "[FAIL] R7 backfill script missing" >&2; exit 12; }

echo "===== R7 MACRO BACKFILL ENV ====="
"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
vals={}
for raw in p.read_text().splitlines():
    if "=" not in raw or raw.lstrip().startswith("#"):
        continue
    k,v=raw.split("=",1)
    vals[k.strip()]=v.strip()
print("TRADING_ECONOMICS_API_KEY=" + ("SET" if vals.get("TRADING_ECONOMICS_API_KEY") else "MISSING"))
print("DATABASE_URL_WRITER=" + ("SET" if vals.get("DATABASE_URL_WRITER") else "MISSING"))
print("DATABASE_URL=" + ("SET" if vals.get("DATABASE_URL") else "MISSING"))
PY

cd "$APP_ROOT"

case "$MODE" in
  smoke)
    exec "$PY" research/r7_macro_backfill.py       --start 2026-08-24 --end 2026-09-02       --chunk-days 10 --max-chunks 1
    ;;
  dry-run)
    exec "$PY" research/r7_macro_backfill.py       --start 2020-01-01 --end 2026-09-02       --chunk-days 90
    ;;
  write)
    echo "[R7-M] WRITE MODE: upserting research backfill rows into macro_release_observation"
    exec "$PY" research/r7_macro_backfill.py       --start 2020-01-01 --end 2026-09-02       --chunk-days 90 --write
    ;;
  *)
    echo "Usage: $0 {smoke|dry-run|write}" >&2
    exit 64
    ;;
esac
