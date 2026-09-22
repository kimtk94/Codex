#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
RESEARCH_PY="$RESEARCH_VENV/bin/python"

[ -x "$RESEARCH_PY" ] || {
  echo "[FAIL] Research Python missing: $RESEARCH_PY" >&2
  exit 10
}

export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$RESEARCH_PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values

p = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
v = dotenv_values(p) if p.exists() else {}
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

OUT="${KALMAN_V3_TRACKER_OUTPUT:-$DATA_ROOT/Market_Model_V3_Shadow/tracker/latest.json}"

mkdir -p "$(dirname "$OUT")"

"$RESEARCH_PY" -m research.model_v3.shadow_tracker   --data-root "$DATA_ROOT"   --output "$OUT"

echo
echo "KALMAN_V3_SHADOW_TRACKER_COMPLETE"
echo "report=$OUT"
echo "production_write=false"
echo "neon_write=false"
echo "trade_execution=false"
