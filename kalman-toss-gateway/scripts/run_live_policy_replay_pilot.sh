#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
MAX_TRADES="${LIVE_POLICY_REPLAY_PILOT_TRADES:-20}"

export KALMAN_ENV_FILE="$ENV_FILE"

echo "===================================================="
echo "LIVE POLICY REPLAY V1 — SAFE PILOT"
echo "===================================================="
echo "app_root=$APP_ROOT"
echo "python=$PY"
echo "env_file=$ENV_FILE"
echo "max_trades=$MAX_TRADES"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[FAIL] env file missing: $ENV_FILE" >&2
  exit 2
fi

if [[ ! -f "$APP_ROOT/research/quant_stack/live_policy_replay.py" ]]; then
  echo "[FAIL] replay module missing under app_root=$APP_ROOT" >&2
  exit 2
fi

echo
echo "===== NON-SECRET LIVE POLICY SNAPSHOT ====="
grep -E '^(AUTO_TRADE_MODEL_ROTATION_ENABLED|AUTO_TRADE_PROFIT_FLIP_GUARD_ENABLED|AUTO_TRADE_PROFIT_FLIP_ARM_PCT|AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT|AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT|AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS|AUTO_TRADE_STOP_LOSS_PCT|AUTO_TRADE_TAKE_PROFIT_PCT)=' "$ENV_FILE" || true

echo
echo "===== GOOGLE DRIVE ====="
if mountpoint -q /mnt/gdrive; then
  echo "[PASS] /mnt/gdrive mounted"
else
  echo "[FAIL] /mnt/gdrive is not mounted" >&2
  exit 3
fi

echo
echo "===== COMPILE ====="
cd "$APP_ROOT" || {
  echo "[FAIL] cannot cd to app_root=$APP_ROOT" >&2
  exit 2
}

"$PY" -m py_compile   app/live_exit_policy.py   research/quant_stack/live_policy_replay.py
COMPILE_RC=$?
if [[ $COMPILE_RC -ne 0 ]]; then
  echo "[FAIL] compile rc=$COMPILE_RC" >&2
  exit "$COMPILE_RC"
fi
echo "[PASS] compile"

echo
echo "===== PILOT RUN ====="
bash scripts/run_live_policy_replay.sh   --max-trades "$MAX_TRADES"   --backfill-only   "$@"
PILOT_RC=$?
if [[ $PILOT_RC -ne 0 ]]; then
  echo "[FAIL] pilot rc=$PILOT_RC" >&2
  exit "$PILOT_RC"
fi

ROOT="$("$PY" - <<'PY'
from research.quant_stack.open_revalidation_backtest import _default_us_etf_root
print(_default_us_etf_root())
PY
)"
STATUS="$ROOT/model_lab_v1/results/live_policy_replay_v1/status.json"

echo
echo "===== PILOT STATUS ====="
if [[ ! -f "$STATUS" ]]; then
  echo "[FAIL] status file missing: $STATUS" >&2
  exit 4
fi
cat "$STATUS"

echo
echo "===== PILOT INTERPRETATION ====="
"$PY" - "$STATUS" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
x = json.loads(p.read_text(encoding="utf-8"))
coverage = x.get("coverage") or {}
rows = int(x.get("rows") or 0)
ready = int(x.get("ready_rows") or 0)
ready_ratio = ready / rows if rows else 0.0
watch = coverage.get("median_watch_coverage")
position = coverage.get("median_position_watch_coverage")
execution = coverage.get("median_execution_watch_coverage")
regular = coverage.get("median_regular_exec_coverage")
overnight = coverage.get("median_overnight_watch_coverage")
trades_with_overnight_rows = coverage.get("trades_with_overnight_feed_rows")
median_overnight_rows = coverage.get("median_overnight_feed_bar_rows")

print(f"status={x.get('status')}")
print(f"rows={rows}")
print(f"ready_rows={ready}")
print(f"ready_ratio={ready_ratio:.3f}")
print(f"median_watch_coverage={watch}")
print(f"median_position_watch_coverage={position}")
print(f"median_execution_watch_coverage={execution}")
print(f"median_regular_exec_coverage={regular}")
print(f"median_overnight_watch_coverage={overnight}")
print(f"trades_with_overnight_feed_rows={trades_with_overnight_rows}")
print(f"median_overnight_feed_bar_rows={median_overnight_rows}")
print(f"production_changed={x.get('production_changed')}")
print(f"automation_changed={x.get('automation_changed')}")

backfill_ok = (
    x.get("status") == "BACKFILL_COMPLETE"
    and rows > 0
    and ready == rows
    and bool(x.get("production_changed")) is False
    and bool(x.get("automation_changed")) is False
)

coverage_ok = (
    watch is not None and float(watch) >= 0.80
    and position is not None and float(position) >= 0.80
    and regular is not None and float(regular) >= 0.95
    and overnight is not None and float(overnight) >= 0.80
)

print("backfill_contract=" + ("PASS" if backfill_ok else "FAIL"))
print("coverage_contract=" + ("PASS" if coverage_ok else "FAIL"))
print("pilot_contract=" + ("PASS" if backfill_ok and coverage_ok else "FAIL"))

if backfill_ok and not coverage_ok:
    print("diagnosis=DATA_SEMANTICS_REVIEW_REQUIRED")
    print("note=Do not run full replay until daytime lastPrice semantics are reconciled.")

raise SystemExit(0 if backfill_ok and coverage_ok else 5)
PY
