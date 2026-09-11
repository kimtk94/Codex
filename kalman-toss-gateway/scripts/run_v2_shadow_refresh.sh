#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
MARKET_VENV="${KALMAN_MARKET_V2_VENV:-/opt/kalman/.venv-market-v2}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PROD_VENV="${KALMAN_PROD_VENV:-/opt/kalman/.venv}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

MIRROR_NEON=false
SKIP_FINVIZ=false

usage() {
  cat <<'EOF'
Usage:
  run_v2_shadow_refresh.sh [--mirror-neon] [--skip-finviz]

Scheduled fixed-model SHADOW refresh:
  1. Market Data V2
  2. TA-Lib Features V2
  3. optional Finviz point-in-time snapshot
  4. fixed-model SHADOW scoring (NO RETRAIN)
  5. Neon SHADOW validation
  6. optional Neon SHADOW mirror

This runner never calls run_model_v2_research.sh.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mirror-neon) MIRROR_NEON=true ;;
    --skip-finviz) SKIP_FINVIZ=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

need_file() {
  [ -f "$1" ] || fail "missing file: $1"
}

need_exec() {
  [ -x "$1" ] || fail "missing executable: $1"
}

mkdir -p "$LOCK_DIR"
exec 9>"$LOCK_DIR/v2-shadow-refresh.lock"
flock -n 9 || fail "V2 fixed-model SHADOW refresh already running"

need_file "$ENV_FILE"
need_file "$APP_ROOT/config/model-v2-spec.json"
need_file "$APP_ROOT/engine/model_v2_neon_writer.py"
need_exec "$MARKET_VENV/bin/python"
need_exec "$RESEARCH_VENV/bin/python"
need_exec "$PROD_VENV/bin/python"
need_exec "$APP_ROOT/scripts/run_market_data_v2.sh"
need_exec "$APP_ROOT/scripts/run_features_v2.sh"
need_exec "$APP_ROOT/scripts/run_finviz_v2.sh"
need_exec "$APP_ROOT/scripts/run_shadow_v2.sh"

export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"
export KALMAN_MARKET_V2_VENV="$MARKET_VENV"
export KALMAN_RESEARCH_V2_VENV="$RESEARCH_VENV"
export KALMAN_PROD_VENV="$PROD_VENV"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PROD_VENV/bin/python" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys

v = dotenv_values(Path(sys.argv[1]))
trading = str(v.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(v.get("LIVE_TRADING_CONFIRM") or "").strip()
mode = str(v.get("AUTO_TRADE_EXECUTION_MODE") or "DRY_RUN").strip().upper()

print("TRADING_ENABLED          =", trading or "(empty)")
print("LIVE_TRADING_CONFIRM     =", "SET" if confirm else "(empty)")
print("AUTO_TRADE_EXECUTION_MODE=", mode)

if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true; refuse scheduled V2 SHADOW refresh")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM is set; refuse scheduled V2 SHADOW refresh")
PY

DATA_ROOT="$("$PROD_VENV/bin/python" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

if [[ "$DATA_ROOT" == /mnt/gdrive* ]]; then
  mountpoint -q /mnt/gdrive || fail "Google Drive mount unavailable"
  timeout 20 ls /mnt/gdrive >/dev/null || fail "Google Drive mount unreadable"
fi

MARKET_ROOT="$("$PROD_VENV/bin/python" - "$ENV_FILE" "$DATA_ROOT" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
root = sys.argv[2]
print(v.get("KALMAN_MARKET_V2_OUTPUT_DIR") or f"{root}/Market_Data/v2")
PY
)"

FEATURE_ROOT="$("$PROD_VENV/bin/python" - "$ENV_FILE" "$DATA_ROOT" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
root = sys.argv[2]
print(v.get("KALMAN_FEATURES_V2_OUTPUT_DIR") or f"{root}/Market_Features/v2")
PY
)"

MODEL_ROOT="$("$PROD_VENV/bin/python" - "$ENV_FILE" "$DATA_ROOT" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
root = sys.argv[2]
print(v.get("KALMAN_MODEL_V2_ROOT") or f"{root}/Market_Model_V2")
PY
)"

MODEL_DIR="$MODEL_ROOT/models"
SHADOW_FILE="$MODEL_ROOT/shadow/latest/shadow_signals.json"
NEON_STATUS="$MODEL_ROOT/shadow/neon_mirror_status.json"

need_file "$MODEL_DIR/us/model.json"
need_file "$MODEL_DIR/kr/model.json"
need_file "$MODEL_DIR/btc/model.json"

echo "=================================================="
echo "Kalman V2 fixed-model SHADOW refresh"
echo "=================================================="
echo "Data root    : $DATA_ROOT"
echo "Model root   : $MODEL_ROOT"
echo "Finviz       : $([ "$SKIP_FINVIZ" = true ] && echo SKIP || echo RUN)"
echo "Neon mirror  : $MIRROR_NEON"
echo "Retrain      : NEVER"
echo

echo "[1/5] Market Data V2"
"$APP_ROOT/scripts/run_market_data_v2.sh"

"$PROD_VENV/bin/python" - "$MARKET_ROOT/market_data_v2_run_status.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
x = json.loads(p.read_text(encoding="utf-8"))
status = str(x.get("status") or "")
print("market_data status:", status)
if status != "READY":
    raise SystemExit(f"[FAIL] scheduled refresh requires Market Data READY, got {status}")
PY

echo
echo "[2/5] TA-Lib Features V2"
"$APP_ROOT/scripts/run_features_v2.sh"

"$PROD_VENV/bin/python" - "$FEATURE_ROOT/features_v2_run_status.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
x = json.loads(p.read_text(encoding="utf-8"))
status = str(x.get("status") or "")
print("features status:", status)
if status != "READY":
    raise SystemExit(f"[FAIL] scheduled refresh requires Features READY, got {status}")
PY

FINVIZ_RC=0
if [ "$SKIP_FINVIZ" = true ]; then
  echo
  echo "[3/5] Finviz: SKIPPED"
else
  echo
  echo "[3/5] Finviz point-in-time snapshot"
  set +e
  "$APP_ROOT/scripts/run_finviz_v2.sh" --force
  FINVIZ_RC=$?
  set -e
  if [ "$FINVIZ_RC" -ne 0 ]; then
    echo "[WARN] Finviz failed with exit=$FINVIZ_RC; fixed-model scoring continues." >&2
  fi
fi

echo
echo "[4/5] Fixed-model SHADOW scoring"
"$APP_ROOT/scripts/run_shadow_v2.sh"
need_file "$SHADOW_FILE"

"$PROD_VENV/bin/python" - "$SHADOW_FILE" <<'PY'
import json, sys
from pathlib import Path

signals = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(signals, list) or len(signals) != 3:
    raise SystemExit(f"[FAIL] expected 3 SHADOW signals, got {len(signals) if isinstance(signals, list) else type(signals).__name__}")

for s in signals:
    if str(s.get("signal") or "").upper() != "SHADOW":
        raise SystemExit("[FAIL] non-SHADOW signal detected")
    if s.get("entry_allowed") is not False:
        raise SystemExit("[FAIL] entry_allowed must be false")

print("shadow signals: 3 / safety gates PASS")
PY

echo
echo "[5/5] Neon SHADOW validation"
"$PROD_VENV/bin/python" -m engine.model_v2_neon_writer   --shadow-file "$SHADOW_FILE"   --model-dir "$MODEL_DIR"   --status-file "$NEON_STATUS"   --dry-run

if [ "$MIRROR_NEON" = true ]; then
  TMP_ENV="$(mktemp /opt/kalman/.env.v2-refresh.XXXXXX)"
  chmod 600 "$TMP_ENV"

  cleanup_tmp_env() {
    if [ -f "$TMP_ENV" ]; then
      if command -v shred >/dev/null 2>&1; then
        shred -u "$TMP_ENV"
      else
        rm -f "$TMP_ENV"
      fi
    fi
  }
  trap cleanup_tmp_env EXIT

  "$PROD_VENV/bin/python" - "$ENV_FILE" "$TMP_ENV" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
remove = {
    "KALMAN_MODEL_V2_NEON_ENABLED",
    "KALMAN_MODEL_V2_NEON_CONFIRM",
}
out = []
for line in src.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0].strip() if "=" in line else ""
    if key not in remove:
        out.append(line)
out += [
    "KALMAN_MODEL_V2_NEON_ENABLED=true",
    "KALMAN_MODEL_V2_NEON_CONFIRM=CONFIRM_NEON_SHADOW_MIRROR",
]
dst.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
dst.chmod(0o600)
PY

  KALMAN_ENV_FILE="$TMP_ENV"   "$PROD_VENV/bin/python" -m engine.model_v2_neon_writer     --shadow-file "$SHADOW_FILE"     --model-dir "$MODEL_DIR"     --status-file "$NEON_STATUS"

  cleanup_tmp_env
  trap - EXIT

  "$PROD_VENV/bin/python" - "$NEON_STATUS" <<'PY'
import json, sys
from pathlib import Path
x = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "status": "MIRRORED",
    "pipeline_db_status": "ABORTED",
    "latest_successful_run_unchanged": True,
    "dashboard_snapshot_created": False,
    "auto_trade_visible": False,
    "transaction_invariants_verified": True,
}
for k, v in expected.items():
    if x.get(k) != v:
        raise SystemExit(f"[FAIL] Neon invariant {k}: {x.get(k)!r} != {v!r}")
print("Neon SHADOW mirror invariants: PASS")
PY
fi

echo
echo "=================================================="
echo "V2_FIXED_SHADOW_REFRESH_COMPLETE"
echo "finviz_exit=$FINVIZ_RC"
echo "neon_mode=$([ "$MIRROR_NEON" = true ] && echo MIRROR || echo DRY_RUN)"
echo "retrain=false"
echo "=================================================="
