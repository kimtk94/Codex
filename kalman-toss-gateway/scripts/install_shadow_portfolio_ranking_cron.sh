#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/install_shadow_portfolio_ranking_cron.sh" >&2
  exit 1
fi

BASE="${KALMAN_BASE:-/opt/kalman}"
APP_ROOT="${KALMAN_APP_ROOT:-$BASE/app}"
ENV_FILE="${KALMAN_ENV_FILE:-$BASE/.env}"
PY="${KALMAN_PYTHON:-$BASE/.venv/bin/python}"
SRC="$APP_ROOT/config/shadow-portfolio-ranking-v2.cron.d"
DST="/etc/cron.d/kalman-shadow-portfolio-ranking"
RUNNER="$APP_ROOT/scripts/run_shadow_portfolio_ranking_v2.sh"
ENGINE="$APP_ROOT/engine/shadow_portfolio_ranking.py"
WRITER="$APP_ROOT/engine/shadow_portfolio_ranking_writer.py"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
ok(){ echo "[OK]   $*"; }

[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"
[ -x "$PY" ] || fail "Python missing: $PY"
[ -f "$SRC" ] || fail "cron source missing: $SRC"
[ -x "$RUNNER" ] || fail "runner missing/not executable: $RUNNER"
[ -f "$ENGINE" ] || fail "engine missing: $ENGINE"
[ -f "$WRITER" ] || fail "writer missing: $WRITER"

bash -n "$RUNNER" || fail "runner shell syntax invalid"
"$PY" -m py_compile "$ENGINE" "$WRITER" || fail "ranking Python compile failed"
ok "runner + Python syntax"

grep -q '^CRON_TZ=Asia/Seoul$' "$SRC" || fail "CRON_TZ missing"
count="$(grep -Ec '^[0-9].*run_shadow_portfolio_ranking_v2.sh --mirror-neon' "$SRC" || true)"
[ "$count" -eq 2 ] || fail "expected exactly 2 active ranking cron lines, found $count"
if grep -q 'run_v2_shadow_refresh' "$SRC"; then
  fail "dedicated cron must not contain V2 refresh jobs"
fi
if grep -q 'run_shadow_portfolio_ranking_v2.sh--' "$SRC"; then
  fail "malformed ranking command detected"
fi
ok "dedicated cron syntax shape"

if [ -f /etc/cron.d/kalman ] && grep -q 'run_shadow_portfolio_ranking_v2.sh' /etc/cron.d/kalman; then
  fail "/etc/cron.d/kalman already contains ranking jobs; remove duplicates first"
fi

readarray -t PATHS < <("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v=dotenv_values(Path(sys.argv[1]))
root=v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data"
market=v.get("KALMAN_MARKET_V2_OUTPUT_DIR") or f"{root}/Market_Data/v2"
model=v.get("KALMAN_MODEL_V2_ROOT") or f"{root}/Market_Model_V2"
output=v.get("KALMAN_SHADOW_RANKING_OUTPUT_DIR") or f"{model}/shadow_portfolio"
print(market)
print(output)
PY
)
MARKET_ROOT="${PATHS[0]}"
OUTPUT_ROOT="${PATHS[1]}"
STATUS_FILE="$OUTPUT_ROOT/latest/neon_mirror_status.json"

if [[ "$MARKET_ROOT" == /mnt/gdrive* || "$OUTPUT_ROOT" == /mnt/gdrive* ]]; then
  systemctl is-active --quiet kalman-gdrive.service || fail "kalman-gdrive.service is not active"
  mountpoint -q /mnt/gdrive || fail "/mnt/gdrive is not mounted"
  timeout 20 ls "$MARKET_ROOT" >/dev/null || fail "Market Data V2 root unreadable: $MARKET_ROOT"
  ok "Google Drive mount"
fi

"$PY" - "$STATUS_FILE" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json, sys

p=Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(f"[FAIL] recent mirror status missing: {p}")
x=json.loads(p.read_text(encoding="utf-8"))
if x.get("status")!="MIRRORED":
    raise SystemExit(f"[FAIL] latest mirror status is not MIRRORED: {x.get('status')}")
if x.get("trade_execution") is not False:
    raise SystemExit("[FAIL] trade_execution invariant is not false")
if x.get("strategy_signal_write") is not False:
    raise SystemExit("[FAIL] strategy_signal_write invariant is not false")
if x.get("dashboard_snapshot_write") is not False:
    raise SystemExit("[FAIL] dashboard_snapshot_write invariant is not false")
ts=x.get("mirrored_at")
if not ts:
    raise SystemExit("[FAIL] mirrored_at missing")
dt=datetime.fromisoformat(ts.replace("Z","+00:00"))
age=(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()
if age < 0 or age > 86400:
    raise SystemExit(f"[FAIL] latest mirror is not within 24h: age={age:.0f}s")
print(f"[OK]   recent isolated Neon mirror ({age:.0f}s old)")
PY

install -d -m 0755 "$BASE/logs"
install -m 0644 "$SRC" "$DST"

if systemctl list-unit-files cron.service >/dev/null 2>&1; then
  systemctl reload cron.service || systemctl restart cron.service
elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
  systemctl reload crond.service || systemctl restart crond.service
else
  fail "cron/crond service not found"
fi

echo
echo "Installed $DST"
grep -n 'run_shadow_portfolio_ranking_v2' "$DST"
echo
echo "TRADING_ENABLED was not changed."
echo "AUTO_TRADE_ENABLED was not changed."
echo "Existing /etc/cron.d/kalman was not modified."
