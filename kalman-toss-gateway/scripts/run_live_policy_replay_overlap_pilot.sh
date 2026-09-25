#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive/US_ETF}"
BOUNDARY_FILE="${LIVE_POLICY_REPLAY_BOUNDARY_FILE:-$ROOT/model_lab_v1/results/live_policy_replay_v1/boats_history_boundary.json}"
OUT_DIR="${LIVE_POLICY_REPLAY_OVERLAP_OUTPUT_DIR:-$ROOT/model_lab_v1/results/live_policy_replay_v1_2025_sip_exact}"
MAX_TRADES="${LIVE_POLICY_REPLAY_PILOT_TRADES:-50}"
END_DATE="${LIVE_POLICY_REPLAY_OVERLAP_END:-2025-12-31}"
PRIMARY_FEED="${LIVE_POLICY_REPLAY_PRIMARY_FEED:-sip}"

export KALMAN_ENV_FILE="$ENV_FILE"

echo "===================================================="
echo "LIVE POLICY REPLAY — BOATS OVERLAP PILOT"
echo "===================================================="
echo "app_root=$APP_ROOT"
echo "boundary_file=$BOUNDARY_FILE"
echo "output_dir=$OUT_DIR"
echo "max_trades=$MAX_TRADES"
echo "end=$END_DATE"
echo "primary_feed=$PRIMARY_FEED"

if [[ ! -f "$BOUNDARY_FILE" ]]; then
  echo "[FAIL] boundary file missing: $BOUNDARY_FILE"
  exit 2
fi

BOUNDARY="$("$PY" - "$BOUNDARY_FILE" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
x = json.loads(p.read_text(encoding="utf-8"))

if not bool(x.get("baseline_overlaps_boats_history")):
    print("")
    raise SystemExit(3)

value = x.get("first_common_candidate_utc")
print("" if value is None else str(value))
PY
)"
BOUNDARY_RC=$?

if [[ $BOUNDARY_RC -ne 0 || -z "$BOUNDARY" ]]; then
  echo "[FAIL] no valid overlap boundary found in $BOUNDARY_FILE"
  echo "boundary_rc=$BOUNDARY_RC"
  exit 3
fi

echo
echo "===== RESOLVED OVERLAP ====="
echo "start=$BOUNDARY"
echo "end=$END_DATE"

mkdir -p "$OUT_DIR"
MKDIR_RC=$?
if [[ $MKDIR_RC -ne 0 ]]; then
  echo "[FAIL] cannot create output dir: $OUT_DIR"
  exit "$MKDIR_RC"
fi

cd "$APP_ROOT"
CD_RC=$?
if [[ $CD_RC -ne 0 ]]; then
  echo "[FAIL] cannot cd to app_root=$APP_ROOT"
  exit "$CD_RC"
fi

echo
echo "===== 50-TRADE VALIDATION PILOT ====="
LIVE_POLICY_REPLAY_PILOT_TRADES="$MAX_TRADES" bash scripts/run_live_policy_replay_pilot.sh   --start "$BOUNDARY"   --end "$END_DATE"   --feed "$PRIMARY_FEED"   --overnight-feed boats   --output-dir "$OUT_DIR"

RC=$?

echo
echo "===== OVERLAP PILOT RESULT ====="
echo "rc=$RC"
echo "status=$OUT_DIR/status.json"
echo "audit=$OUT_DIR/live_policy_replay_trade_audit.parquet"
echo "event_audit=$OUT_DIR/live_policy_replay_event_audit.parquet"

if [[ $RC -eq 0 ]]; then
  echo "[PASS] overlap pilot is validation-ready"
else
  echo "[FAIL] overlap pilot needs review before full replay"
fi

exit "$RC"
