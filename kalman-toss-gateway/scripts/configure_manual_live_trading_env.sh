#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
SERVICE="${KALMAN_GATEWAY_SERVICE:-kalman-toss-gateway.service}"
MODE="${1:-status}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo $0 [enable|disable|status]" >&2
  exit 1
fi

[ -f "$ENV_FILE" ] || {
  echo "[FAIL] env file missing: $ENV_FILE" >&2
  exit 2
}

case "$MODE" in
  enable|disable|status) ;;
  *)
    echo "Usage: sudo $0 [enable|disable|status]" >&2
    exit 3
    ;;
esac

if [ "$MODE" = "status" ]; then
  grep -E '^(MANUAL_TRADING_ENABLED|MANUAL_TRADING_CONFIRM|AUTO_TRADE_ENABLED|AUTO_TRADE_EXECUTION_MODE|TRADING_ENABLED|LIVE_TRADING_CONFIRM)=' "$ENV_FILE" || true
  echo
  systemctl is-active "$SERVICE" 2>/dev/null || true
  curl -fsS --max-time 5 http://127.0.0.1:8787/health || true
  echo
  exit 0
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${ENV_FILE}.bak.manual.${STAMP}"
cp -a "$ENV_FILE" "$BACKUP"
chmod 0600 "$BACKUP"

if [ "$MODE" = "enable" ]; then
  MANUAL_ENABLED=true
  MANUAL_CONFIRM=CONFIRM_MANUAL_TRADING
else
  MANUAL_ENABLED=false
  MANUAL_CONFIRM=
fi

MANUAL_ENABLED="$MANUAL_ENABLED" MANUAL_CONFIRM="$MANUAL_CONFIRM" python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])

values = {
    "MANUAL_TRADING_ENABLED": os.environ["MANUAL_ENABLED"],
    "MANUAL_TRADING_CONFIRM": os.environ["MANUAL_CONFIRM"],
    # Automatic execution remains explicitly disarmed.
    "AUTO_TRADE_ENABLED": "false",
    "AUTO_TRADE_EXECUTION_MODE": "DRY_RUN",
    "AUTO_TRADE_SHADOW_CONFIRM": "",
    "TRADING_ENABLED": "false",
    "LIVE_TRADING_CONFIRM": "",
}

lines = path.read_text(encoding="utf-8").splitlines()
out = []
seen = set()

for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        out.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in values:
        if key not in seen:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        continue
    out.append(line)

missing = [key for key in values if key not in seen]
if missing:
    if out and out[-1] != "":
        out.append("")
    out.append("# --- Manual live trading gate ---")
    for key in missing:
        out.append(f"{key}={values[key]}")

tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(path)
path.chmod(0o600)
PY

systemctl restart "$SERVICE"

for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1:8787/health >/tmp/kalman-manual-health.json 2>/dev/null; then
    break
  fi
  sleep 1
done

python3 - /tmp/kalman-manual-health.json "$MODE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
mode = sys.argv[2]
x = json.loads(path.read_text(encoding="utf-8"))

assert x.get("status") == "ok"
assert x.get("tradingEnabled") is False
assert x.get("liveGateOpen") is False

expected = mode == "enable"
assert x.get("manualTradingEnabled") is expected
assert x.get("manualLiveGateOpen") is expected

print("MANUAL_LIVE_GATE=" + ("OPEN" if expected else "CLOSED"))
print("AUTO_LIVE_GATE=CLOSED")
PY

echo
echo "Updated: $ENV_FILE"
echo "Backup : $BACKUP"
echo

grep -E '^(MANUAL_TRADING_ENABLED|MANUAL_TRADING_CONFIRM|AUTO_TRADE_ENABLED|AUTO_TRADE_EXECUTION_MODE|TRADING_ENABLED|LIVE_TRADING_CONFIRM)=' "$ENV_FILE" || true

echo
echo "Manual live order endpoint: POST /api/orders/live"
echo "Automatic trading remains disabled."
