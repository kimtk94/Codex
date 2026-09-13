#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Kalman Forward SHADOW Bake-off V1 — One-Sheet Server Setup
#
# What this does:
#   1) preflight / safety checks
#   2) compile + unit tests
#   3) persist safe bake-off defaults into /opt/kalman/.env if missing
#   4) install cron (Tue-Sat 08:10 KST)
#   5) run one manual freshness-gated SHADOW cycle
#   6) print health
#
# What this NEVER does:
#   - live trading
#   - Toss order execution
#   - Neon write
#   - production dashboard write
# ==============================================================================

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$RESEARCH_VENV/bin/python"

DAILY="$APP_ROOT/scripts/run_shadow_bakeoff_daily.sh"
INSTALLER="$APP_ROOT/scripts/install_shadow_bakeoff_v1_cron.sh"
HEALTH="$APP_ROOT/scripts/check_shadow_bakeoff_v1.sh"
SCORER="$APP_ROOT/research/shadow_bakeoff/forward_scorer.py"
RUNNER="$APP_ROOT/research/shadow_bakeoff/runner.py"
FRESHNESS="$APP_ROOT/research/shadow_bakeoff/source_freshness.py"
TEST1="$APP_ROOT/tests/test_shadow_bakeoff_v1.py"
TEST2="$APP_ROOT/tests/test_shadow_bakeoff_source_freshness.py"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

echo "============================================================"
echo "Kalman Forward SHADOW Bake-off V1 — One-Sheet Setup"
echo "============================================================"
echo "APP_ROOT : $APP_ROOT"
echo "ENV_FILE : $ENV_FILE"
echo

[ -d "$APP_ROOT" ] || fail "app root missing: $APP_ROOT"
[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"
[ -x "$PY" ] || fail "research python missing: $PY"

for f in   "$DAILY"   "$INSTALLER"   "$HEALTH"   "$SCORER"   "$RUNNER"   "$FRESHNESS"   "$TEST1"   "$TEST2"
do
  [ -f "$f" ] || fail "required file missing: $f"
done

export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"
export KALMAN_RESEARCH_V2_VENV="$RESEARCH_VENV"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[1/6] Safety preflight"
"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys

env = dotenv_values(Path(sys.argv[1]))
trading = str(env.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(env.get("LIVE_TRADING_CONFIRM") or "").strip()

print("TRADING_ENABLED      =", trading or "(empty)")
print("LIVE_TRADING_CONFIRM =", "SET" if confirm else "(empty)")

if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM is set")
print("SAFETY_PREFLIGHT=PASS")
PY

echo
echo "[2/6] Compile + unit tests"
cd "$APP_ROOT"
"$PY" -m py_compile   "$SCORER"   "$RUNNER"   "$FRESHNESS"   "$TEST1"   "$TEST2"

"$PY" -m pytest -q   tests/test_shadow_bakeoff_v1.py   tests/test_shadow_bakeoff_source_freshness.py

echo
echo "[3/6] Persist safe scheduler defaults"
"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8") if path.exists() else ""

defaults = {
    "KALMAN_SHADOW_BAKEOFF_REFRESH_CURRENT_V2": "true",
    "KALMAN_SHADOW_BAKEOFF_SEED_END": "2026-09-11T00:00:00+00:00",
    "KALMAN_SHADOW_BAKEOFF_SOURCE_REFRESH_SCRIPT": "",
}

existing = set()
for line in text.splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    existing.add(s.split("=", 1)[0].strip())

append = []
for key, value in defaults.items():
    if key not in existing:
        append.append(f"{key}={value}")

if append:
    with path.open("a", encoding="utf-8") as fh:
        if text and not text.endswith("\n"):
            fh.write("\n")
        fh.write("\n# Kalman Forward SHADOW Bake-off V1\n")
        for line in append:
            fh.write(line + "\n")
    print("Added defaults:")
    for line in append:
        print(" ", line)
else:
    print("Bake-off env defaults already present; nothing changed.")
PY

echo
echo "[4/6] Install system cron"
/bin/bash "$INSTALLER" --install

echo
echo "[5/6] Manual freshness-gated SHADOW smoke"
set +e
/bin/bash "$DAILY"
SMOKE_RC=$?
set -e

if [ "$SMOKE_RC" -ne 0 ]; then
  fail "manual SHADOW smoke failed with exit=$SMOKE_RC"
fi

echo
echo "[6/6] Health"
/bin/bash "$HEALTH"

echo
echo "============================================================"
echo "SETUP COMPLETE"
echo "============================================================"
echo "Cron:"
/bin/bash "$INSTALLER" --show
echo
echo "Safety:"
echo "  production_write = FALSE"
echo "  neon_write       = FALSE"
echo "  toss_execution   = FALSE"
echo "  live_execution   = FALSE"
echo
echo "Useful commands:"
echo "  /bin/bash $DAILY"
echo "  /bin/bash $HEALTH"
echo "  sudo /bin/bash $INSTALLER --show"
echo "  sudo /bin/bash $INSTALLER --remove"
