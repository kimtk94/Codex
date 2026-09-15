#!/usr/bin/env bash
set -euo pipefail

REPO="${KALMAN_REPO_ROOT:-/opt/kalman/src/Codex}"
SRC="${KALMAN_SOURCE_ROOT:-$REPO/kalman-toss-gateway}"
APP="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"

fail(){ echo "[FAIL] $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run as root"
[ -d "$SRC" ] || fail "source missing: $SRC"
[ -d "$APP" ] || fail "app missing: $APP"
[ -f "$ENV" ] || fail "env missing: $ENV"

echo "============================================================"
echo "KALMAN MAIN HUB — SAFE vNext.7.4.13 PROMOTION"
echo "============================================================"
echo "Production: $PROD_URL"

echo
echo "[1/6] Sync runtime source"
cp -a "$SRC/." "$APP/"
chmod +x "$APP"/scripts/*.sh
echo "RUNTIME_SYNC=PASS"

echo
echo "[1b/6] CRYPTO rclone XLSX preflight"

PYTHONPATH="$APP" /opt/kalman/.venv/bin/python - <<'PY'
from engine.crypto_sheet_file_compat import resolve_crypto_archive_xlsx, _Workbook

p=resolve_crypto_archive_xlsx()
book=_Workbook(p)
for name in ("Overview","KRW_BTC_4H","KRW_ETH_4H"):
    ws=book.worksheet(name)
    rows=ws.get_all_values()
    if not rows:
        raise SystemExit(f"[FAIL] empty CRYPTO worksheet: {name}")
print("CRYPTO_XLSX=PASS")
print("crypto_archive=",p)
PY

echo
echo "[2/6] Refresh Unified DB + verify read-only account"
KALMAN_APP_ROOT="$APP" \
KALMAN_ENV_FILE="$ENV" \
KALMAN_HUB_PROD_URL="$PROD_URL" \
/bin/bash "$APP/scripts/repair_investment_hub_sync.sh"
echo "MAIN_DATA_REFRESH=PASS"

echo
echo "[3/6] Verify standalone SHADOW snapshot before main promotion"
curl -fsS --max-time 30 \
  "https://kalman-shadow-readonly.vercel.app/api/shadow?ts=$(date +%s)" \
  > /tmp/kalman-main-shadow-preflight.json

python3 - /tmp/kalman-main-shadow-preflight.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="READY", x
assert x.get("schema_version")=="kalman-shadow-readonly-v1", x
inv=x.get("invariants") or {}
assert inv.get("read_only") is True, inv
assert inv.get("trade_execution") is False, inv
assert all(k in (x.get("signals") or {}) for k in ("US","KR","BTC")), x
print("SHADOW_PREFLIGHT=PASS")
print("shadow_updated_at=",x.get("updated_at"))
PY

echo
echo "[4/6] Build, smoke-test, and promote 12-function main candidate"
KALMAN_APP_ROOT="$APP" \
KALMAN_ENV_FILE="$ENV" \
KALMAN_HUB_PROD_URL="$PROD_URL" \
/bin/bash "$APP/scripts/deploy_investment_hub_account_krw.sh"
echo "MAIN_PROMOTION=PASS"

echo
echo "[5/6] Production verification"
curl -fsS --max-time 30 "$PROD_URL/api/health?ts=$(date +%s)" > /tmp/kalman-main-health.json
curl -fsS --max-time 30 "$PROD_URL/api/account?ts=$(date +%s)" > /tmp/kalman-main-account.json
curl -fsS --max-time 30 "$PROD_URL/api/dashboard?market=GLOBAL&ts=$(date +%s)" > /tmp/kalman-main-global.json
curl -fsS --max-time 30 "$PROD_URL/api/dashboard?market=SHADOW&ts=$(date +%s)" > /tmp/kalman-main-shadow.json
curl -fsS --max-time 30 "$PROD_URL/app.js?ts=$(date +%s)" > /tmp/kalman-main-app.js

python3 - \
  /tmp/kalman-main-health.json \
  /tmp/kalman-main-account.json \
  /tmp/kalman-main-global.json \
  /tmp/kalman-main-shadow.json <<'PY'
from datetime import datetime, timezone
import json,sys

h,a,g,s=(json.load(open(p,encoding="utf-8")) for p in sys.argv[1:])

assert h.get("investment_hub_version")=="vNext.7.4.13", h
assert h.get("trade_enabled") is False, h
assert h.get("account_trade_execution") is False, h

assert a.get("status")=="READY", a
assert a.get("trade_execution") is False, a
parts=a.get("parts") or {}
for k in ("accounts","holdings","buying_power_usd","buying_power_krw"):
    assert (parts.get(k) or {}).get("ok") is True, (k,parts.get(k))

assert not g.get("error"), g
assert g.get("payload") is not None, g

generated=g.get("generated_at")
if generated:
    dt=datetime.fromisoformat(str(generated).replace("Z","+00:00"))
    age=(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()
    print("global_generated_at=",generated)
    print("global_age_sec=",round(age))
    assert age < 6*3600, f"GLOBAL snapshot too old: {age}s"

assert s.get("status")=="READY", s
assert s.get("schema_version")=="kalman-shadow-readonly-v1", s
inv=s.get("invariants") or {}
assert inv.get("read_only") is True, inv
assert inv.get("trade_execution") is False, inv
assert all(k in (s.get("signals") or {}) for k in ("US","KR","BTC")), s

print("PRODUCTION_HEALTH=PASS")
print("PRODUCTION_ACCOUNT=PASS")
print("PRODUCTION_GLOBAL=PASS")
print("PRODUCTION_SHADOW=PASS")
PY

grep -q "accountKrw" /tmp/kalman-main-app.js || fail "production app missing accountKrw"
grep -q "renderShadow" /tmp/kalman-main-app.js || fail "production app missing renderShadow"
grep -q "fmt(qty(h),6)" /tmp/kalman-main-app.js || fail "production app missing fractional quantity precision"
echo "PRODUCTION_UI=PASS"

echo
echo "[6/6] Trading safety"
/bin/bash "$APP/scripts/trading_status.sh"

echo
echo "============================================================"
echo "KALMAN_MAIN_COMPLETE"
echo "============================================================"
echo "URL=$PROD_URL"
echo "VERSION=vNext.7.4.13"
echo "API_FUNCTIONS=12"
echo "ACCOUNT=READY"
echo "SHADOW=READ_ONLY_STANDALONE_SNAPSHOT_PROXY"
echo "AUTO_TRADE=false"
echo "============================================================"
