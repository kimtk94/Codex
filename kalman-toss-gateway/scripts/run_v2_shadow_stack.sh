#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
MARKET_VENV="${KALMAN_MARKET_V2_VENV:-/opt/kalman/.venv-market-v2}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PROD_VENV="${KALMAN_PROD_VENV:-/opt/kalman/.venv}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

MIRROR_NEON=false
INSTALL_MISSING=false
SKIP_FINVIZ=false

usage() {
  cat <<'EOF'
Usage:
  run_v2_shadow_stack.sh [--mirror-neon] [--install-missing] [--skip-finviz]

Default behavior:
  1. Market Data V2
  2. TA-Lib Features V2
  3. Finviz point-in-time snapshot (manual --force)
  4. Model V2 retrain + file SHADOW
  5. Neon mirror validation in --dry-run mode

--mirror-neon
  After dry-run validation, perform one real Neon SHADOW mirror.
  The script temporarily enables only the Neon shadow gate in a protected
  copy of /opt/kalman/.env and deletes that temporary file afterward.

--install-missing
  Install missing Market V2 / Research V2 isolated environments.

--skip-finviz
  Skip Finviz. Useful when Finviz is unavailable/rate-limited.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mirror-neon) MIRROR_NEON=true ;;
    --install-missing) INSTALL_MISSING=true ;;
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
exec 9>"$LOCK_DIR/v2-shadow-stack.lock"
flock -n 9 || fail "V2 shadow stack is already running"

need_file "$ENV_FILE"
need_file "$APP_ROOT/config/market-data-v2-universe.json"
need_file "$APP_ROOT/config/model-v2-spec.json"
need_file "$APP_ROOT/engine/model_v2_neon_writer.py"

if [ ! -x "$MARKET_VENV/bin/python" ]; then
  if [ "$INSTALL_MISSING" = true ]; then
    KALMAN_APP_ROOT="$APP_ROOT"     KALMAN_MARKET_V2_VENV="$MARKET_VENV"       "$APP_ROOT/scripts/install_market_tools_v2.sh"
  else
    fail "Market V2 venv missing: $MARKET_VENV (use --install-missing)"
  fi
fi

if [ ! -x "$RESEARCH_VENV/bin/python" ]; then
  if [ "$INSTALL_MISSING" = true ]; then
    KALMAN_APP_ROOT="$APP_ROOT"     KALMAN_RESEARCH_V2_VENV="$RESEARCH_VENV"       "$APP_ROOT/scripts/install_market_research_v2.sh"
  else
    fail "Research V2 venv missing: $RESEARCH_VENV (use --install-missing)"
  fi
fi

need_exec "$PROD_VENV/bin/python"
need_exec "$APP_ROOT/scripts/run_market_data_v2.sh"
need_exec "$APP_ROOT/scripts/run_features_v2.sh"
need_exec "$APP_ROOT/scripts/run_finviz_v2.sh"
need_exec "$APP_ROOT/scripts/run_model_v2_research.sh"

export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"
export KALMAN_MARKET_V2_VENV="$MARKET_VENV"
export KALMAN_RESEARCH_V2_VENV="$RESEARCH_VENV"
export KALMAN_PROD_VENV="$PROD_VENV"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "=================================================="
echo "Kalman V2 SHADOW stack"
echo "=================================================="
echo "APP_ROOT      : $APP_ROOT"
echo "ENV_FILE      : $ENV_FILE"
echo "Market venv   : $MARKET_VENV"
echo "Research venv : $RESEARCH_VENV"
echo "Neon mirror   : $MIRROR_NEON"
echo "Finviz        : $([ "$SKIP_FINVIZ" = true ] && echo SKIP || echo FORCE_MANUAL)"
echo

# Keep research/shadow refresh isolated while production live trading is open.
"$PROD_VENV/bin/python" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys

p = Path(sys.argv[1])
v = dotenv_values(p)
trading = str(v.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(v.get("LIVE_TRADING_CONFIRM") or "").strip()
mode = str(v.get("AUTO_TRADE_EXECUTION_MODE") or "DRY_RUN").strip().upper()

print("TRADING_ENABLED          =", trading or "(empty)")
print("LIVE_TRADING_CONFIRM     =", "SET" if confirm else "(empty)")
print("AUTO_TRADE_EXECUTION_MODE=", mode)

if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true; close live trading before V2 research refresh")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM is set; clear it before V2 research refresh")
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

echo
echo "[1/5] Market Data V2"
"$APP_ROOT/scripts/run_market_data_v2.sh"

echo
echo "[2/5] TA-Lib Features V2"
"$APP_ROOT/scripts/run_features_v2.sh"

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
    echo "[WARN] Finviz failed with exit=$FINVIZ_RC; continuing because model V2 does not consume Finviz directly." >&2
  fi
fi

echo
echo "[4/5] Model V2 retrain + file SHADOW"
"$APP_ROOT/scripts/run_model_v2_research.sh"

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

need_file "$SHADOW_FILE"

echo
echo "[5/5] Neon SHADOW validation (dry-run)"
"$PROD_VENV/bin/python" -m engine.model_v2_neon_writer   --shadow-file "$SHADOW_FILE"   --model-dir "$MODEL_DIR"   --status-file "$NEON_STATUS"   --dry-run

if [ "$MIRROR_NEON" = true ]; then
  echo
  echo "[5b/5] Neon SHADOW mirror"

  TMP_ENV="$(mktemp /opt/kalman/.env.v2-shadow.XXXXXX)"
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
    if key in remove:
        continue
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
fi

echo
echo "=================================================="
echo "V2 SHADOW stack summary"
echo "=================================================="

"$PROD_VENV/bin/python" - "$ENV_FILE" "$DATA_ROOT" "$MODEL_ROOT" "$FINVIZ_RC" "$MIRROR_NEON" <<'PY'
import json
import sys
from pathlib import Path
from dotenv import dotenv_values

env_file = Path(sys.argv[1])
data_root = Path(sys.argv[2])
model_root = Path(sys.argv[3])
finviz_rc = int(sys.argv[4])
mirror = sys.argv[5].lower() == "true"
v = dotenv_values(env_file)

paths = {
    "market_data": Path(v.get("KALMAN_MARKET_V2_OUTPUT_DIR") or data_root / "Market_Data/v2") / "market_data_v2_run_status.json",
    "features": Path(v.get("KALMAN_FEATURES_V2_OUTPUT_DIR") or data_root / "Market_Features/v2") / "features_v2_run_status.json",
    "finviz": Path(v.get("KALMAN_FINVIZ_OUTPUT_DIR") or data_root / "Market_Screeners/finviz") / "finviz_run_status.json",
    "neon": model_root / "shadow/neon_mirror_status.json",
    "shadow": model_root / "shadow/latest/shadow_signals.json",
}

def read_status(path):
    if not path.exists():
        return "MISSING"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"INVALID:{type(exc).__name__}"
    if isinstance(obj, dict):
        return str(obj.get("status") or "OK")
    if isinstance(obj, list):
        return f"READY({len(obj)} signals)"
    return "UNKNOWN"

for name, path in paths.items():
    print(f"{name:<12}: {read_status(path):<20} {path}")

print(f"finviz_exit : {finviz_rc}")
print(f"neon_mode   : {'MIRROR' if mirror else 'DRY_RUN'}")
print("production_writes: Neon SHADOW only when neon_mode=MIRROR")
print("auto_trade visibility: expected FALSE by writer invariants")
PY

echo
echo "V2_SHADOW_STACK_COMPLETE"
