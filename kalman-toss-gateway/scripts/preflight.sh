#!/usr/bin/env bash
set -uo pipefail
BASE="${KALMAN_BASE:-/opt/kalman}"
APP_ROOT="${KALMAN_APP_ROOT:-$BASE/app}"
ENV_FILE="${KALMAN_ENV_FILE:-$BASE/.env}"
PY="${KALMAN_PYTHON:-$BASE/.venv/bin/python}"
FAIL=0
export KALMAN_ENV_FILE="$ENV_FILE"
export KALMAN_APP_ROOT="$APP_ROOT"

ok(){ printf '[OK]   %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; FAIL=1; }

printf 'Kalman server preflight\n'
printf '  app: %s\n  env: %s\n' "$APP_ROOT" "$ENV_FILE"

for c in curl flock systemctl; do
  command -v "$c" >/dev/null 2>&1 && ok "$c available" || fail "$c is missing"
done
[ -x "$PY" ] && ok "Python venv available" || fail "Python venv missing: $PY"
[ -f "$ENV_FILE" ] && ok ".env exists" || fail ".env missing: $ENV_FILE"
[ -d "$APP_ROOT/engine" ] && ok "engine directory exists" || fail "engine directory missing"

if [ -x "$PY" ] && [ -f "$ENV_FILE" ] && [ -d "$APP_ROOT/engine" ]; then
  "$PY" - <<'PY' || FAIL=1
from __future__ import annotations
import base64, binascii, hashlib, lzma, os, re
from pathlib import Path
from dotenv import dotenv_values

app = Path(os.environ['KALMAN_APP_ROOT'])
env_path = Path(os.environ['KALMAN_ENV_FILE'])
env = {k: (v or '') for k, v in dotenv_values(env_path).items()}

def ok(msg): print('[OK]  ', msg)
def warn(msg): print('[WARN]', msg)
def fail(msg):
    print('[FAIL]', msg)
    raise SystemExit(2)

if env.get('TRADING_ENABLED', '').lower() == 'true':
    fail('TRADING_ENABLED=true; deployment preflight requires trading OFF')
if env.get('AUTO_TRADE_ENABLED', '').lower() == 'true':
    fail('AUTO_TRADE_ENABLED=true; deployment preflight requires auto trade OFF')
if env.get('LIVE_TRADING_CONFIRM'):
    fail('LIVE_TRADING_CONFIRM is set; clear it during deployment')
ok('live trading gates are closed')

root = app / 'engine'
parts = sorted(root.glob('_unified_payload_*.b64'))
expected_names = [f'_unified_payload_{i:02d}.b64' for i in range(15)]
names = [p.name for p in parts]
if names != expected_names:
    fail(f'payload file set mismatch: expected={expected_names!r}, actual={names!r}')

encoded_parts = []
for p in parts:
    try:
        text = p.read_text(encoding='ascii')
    except UnicodeDecodeError:
        fail(f'{p.name}: payload is not ASCII')
    compact = ''.join(text.split())
    bad = sorted(set(re.sub(r'[A-Za-z0-9+/=]', '', compact)))
    if bad:
        fail(f'{p.name}: invalid Base64 characters: {bad!r}')
    if len(compact) % 4 != 0:
        fail(f'{p.name}: Base64 length {len(compact)} is not divisible by 4')
    encoded_parts.append(compact)
    print(f'[OK]   {p.name}: {len(compact)} Base64 chars')

encoded = ''.join(encoded_parts)
if len(encoded) != 70688:
    fail(f'Unified payload encoded length mismatch: {len(encoded)} != 70688')
try:
    packed = base64.b64decode(encoded, validate=True)
except binascii.Error as exc:
    fail(f'Unified payload Base64 decode failed: {exc}')
try:
    raw = lzma.decompress(packed)
except lzma.LZMAError as exc:
    fail(f'Unified payload LZMA decompression failed: {exc}')
sha = hashlib.sha256(raw).hexdigest()
expected = 'e1d68ef0744b1083be8c4ba32908f090e0f0b70742cb224df75c9596d06540f8'
if sha != expected:
    fail(f'Unified payload SHA mismatch: {sha} != {expected}')
try:
    compile(raw.decode('utf-8'), 'Investment_Hub_Unified_Colab_v1.server.py', 'exec')
except Exception as exc:
    fail(f'Unified source compile failed: {type(exc).__name__}: {exc}')
ok(f'Unified payload integrity verified: bytes={len(raw)} sha256={sha}')

if not env.get('DATABASE_URL_WRITER'):
    fail('DATABASE_URL_WRITER is empty')
ok('required pipeline secret DATABASE_URL_WRITER is present')

for key in ['KRX_ID','KRX_PW','FRED_API_KEY','ECOS_API_KEY','ALPACA_API_KEY','ALPACA_API_SECRET']:
    if not env.get(key):
        warn(f'{key} is empty; related fallback/input may be unavailable')

if not env.get('TOSS_CLIENT_ID') or not env.get('TOSS_CLIENT_SECRET'):
    warn('Toss OAuth credentials are incomplete; Toss read-only smoke test will be skipped')
if not env.get('HUB_GATEWAY_SECRET'):
    warn('HUB_GATEWAY_SECRET is empty; protected local gateway endpoints cannot be tested')
PY
fi

if [ "$FAIL" -eq 0 ]; then
  "$PY" - <<'PY' || FAIL=1
import os
from dotenv import load_dotenv
load_dotenv(os.environ['KALMAN_ENV_FILE'], override=False)
import psycopg
url = os.environ['DATABASE_URL_WRITER']
with psycopg.connect(url, connect_timeout=10) as conn, conn.cursor() as cur:
    cur.execute('select current_database(), now()')
    db, now = cur.fetchone()
print(f'[OK]   Neon reachable: database={db}, server_time={now}')
PY
fi

DATA_ROOT=/opt/kalman/data
EXPECTED_IP=
if [ -x "$PY" ] && [ -f "$ENV_FILE" ]; then
  DATA_ROOT="$($PY - <<'PY'
import os
from dotenv import dotenv_values
v=dotenv_values(os.environ['KALMAN_ENV_FILE'])
print(v.get('KALMAN_DATA_ROOT') or '/opt/kalman/data')
PY
)"
  EXPECTED_IP="$($PY - <<'PY'
import os
from dotenv import dotenv_values
v=dotenv_values(os.environ['KALMAN_ENV_FILE'])
print(v.get('EXPECTED_EGRESS_IP') or '')
PY
)"
fi

for d in Finance_KR Upbit_BTC; do
  [ -d "$DATA_ROOT/$d" ] && ok "data directory: $DATA_ROOT/$d" || warn "data directory missing: $DATA_ROOT/$d"
done

if [ -n "$EXPECTED_IP" ]; then
  ACTUAL_IP="$(curl -4fsS --max-time 8 https://api.ipify.org 2>/dev/null || true)"
  if [ -z "$ACTUAL_IP" ]; then
    warn 'could not resolve current public egress IP'
  elif [ "$ACTUAL_IP" = "$EXPECTED_IP" ]; then
    ok "public egress IP matches EXPECTED_EGRESS_IP ($ACTUAL_IP)"
  else
    fail "public egress IP mismatch: actual=$ACTUAL_IP expected=$EXPECTED_IP"
  fi
else
  warn 'EXPECTED_EGRESS_IP is empty; Toss IP allowlist cannot be verified'
fi

if systemctl is-active --quiet kalman-toss-gateway 2>/dev/null; then
  ok 'kalman-toss-gateway service is active'
else
  warn 'kalman-toss-gateway service is not active yet'
fi

if [ "$FAIL" -eq 0 ]; then
  printf '[PASS] Kalman preflight passed.\n'
else
  printf '[STOP] Fix FAIL items before enabling cron.\n'
fi
exit "$FAIL"
