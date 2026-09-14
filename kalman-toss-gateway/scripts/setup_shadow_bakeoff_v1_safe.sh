#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$RESEARCH_VENV/bin/python"

SCORER="$APP_ROOT/research/shadow_bakeoff/forward_scorer.py"
RUNNER="$APP_ROOT/research/shadow_bakeoff/runner.py"
FRESHNESS="$APP_ROOT/research/shadow_bakeoff/source_freshness.py"
GUARDED="$APP_ROOT/scripts/run_shadow_bakeoff_guarded.sh"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

echo "============================================================"
echo "Kalman Forward SHADOW Bake-off V1 — SAFE INSTALL ONLY"
echo "============================================================"

[ -d "$APP_ROOT" ] || fail "app root missing: $APP_ROOT"
[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"
[ -x "$PY" ] || fail "research python missing: $PY"

for f in "$SCORER" "$RUNNER" "$FRESHNESS" "$GUARDED"; do
  [ -f "$f" ] || fail "required file missing: $f"
done

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[1/4] Live safety gate"
"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
trading = str(v.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(v.get("LIVE_TRADING_CONFIRM") or "").strip()
if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM is set")
print("LIVE_SAFETY_GATE=PASS")
PY

echo "[2/4] Lightweight syntax validation"
"$PY" -m py_compile "$SCORER" "$RUNNER" "$FRESHNESS"

echo "[3/4] Persist conservative resource defaults"
"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
existing = {
    line.split("=", 1)[0].strip()
    for line in text.splitlines()
    if line.strip() and not line.lstrip().startswith("#") and "=" in line
}
defaults = {
    "KALMAN_SHADOW_BAKEOFF_REFRESH_CURRENT_V2": "true",
    "KALMAN_SHADOW_BAKEOFF_SEED_END": "2026-09-11T00:00:00+00:00",
    "KALMAN_SHADOW_BAKEOFF_SOURCE_REFRESH_SCRIPT": "",
    "KALMAN_SHADOW_BAKEOFF_MEMORY_MAX": "1536M",
    "KALMAN_SHADOW_BAKEOFF_CPU_QUOTA": "75%",
    "KALMAN_SHADOW_BAKEOFF_TIMEOUT_SEC": "5400",
}
missing = [(k, v) for k, v in defaults.items() if k not in existing]
if missing:
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n# Kalman Forward SHADOW Bake-off V1 safe resource limits\n")
        for k, v in missing:
            fh.write(f"{k}={v}\n")
for k, v in missing:
    print(f"ADDED {k}={v}")
if not missing:
    print("No env changes needed")
PY

echo "[4/4] Ensure old cron is disabled"
rm -f /etc/cron.d/kalman-shadow-bakeoff-v1

echo
echo "SAFE_INSTALL_COMPLETE"
echo "No pytest was run."
echo "No model fitting was run."
echo "No cron was installed."
echo "No SHADOW smoke was run."
echo
echo "When ready, start one resource-capped run with:"
echo "  /bin/bash $GUARDED"
echo
echo "Monitor it with:"
echo "  systemctl status kalman-shadow-bakeoff-v1.service --no-pager"
echo "  journalctl -u kalman-shadow-bakeoff-v1.service -f"
