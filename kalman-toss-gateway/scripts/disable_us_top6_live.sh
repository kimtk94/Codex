#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/disable_us_top6_live.sh" >&2
  exit 1
fi

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"

[ -f "$ENV_FILE" ] || { echo "[FAIL] missing $ENV_FILE" >&2; exit 2; }

"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
updates={
    "AUTO_TRADE_ENABLED":"false",
    "AUTO_TRADE_EXECUTION_MODE":"DRY_RUN",
    "AUTO_TRADE_US_TOP6_CONFIRM":"",
    "TRADING_ENABLED":"false",
    "LIVE_TRADING_CONFIRM":"",
}
lines=path.read_text(encoding="utf-8").splitlines()
out=[]
seen=set()
for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        out.append(line); continue
    key=line.split("=",1)[0].strip()
    if key in updates:
        if key not in seen:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
    else:
        out.append(line)
for key,val in updates.items():
    if key not in seen:
        out.append(f"{key}={val}")
tmp=path.with_suffix(path.suffix+".tmp")
tmp.write_text("\n".join(out).rstrip()+"\n",encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(path)
path.chmod(0o600)
PY

systemctl restart kalman-toss-gateway.service

for _ in $(seq 1 20); do
  if curl -fsS --max-time 5 http://127.0.0.1:8787/health >/tmp/kalman-us-top6-health.json 2>/dev/null; then
    break
  fi
  sleep 1
done

"$PY" - /tmp/kalman-us-top6-health.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("tradingEnabled") is False,x
assert x.get("liveGateOpen") is False,x
print("[PASS] automated live trading DISABLED")
PY
