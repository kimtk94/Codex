#!/usr/bin/env bash
set -euo pipefail

# Presentation-only correction for the Investment Hub header.
# The web remains read-only. This script MUST NOT enable order execution.

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"
BASE_DEPLOYMENT="${KALMAN_HUB_BASE_DEPLOYMENT:-dpl_99ZABqst9m2kpnphkYkLJ5gJ1RQs}"
VERSION_TAG="${KALMAN_HUB_VERSION_TAG:-vNext.7.4.19}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY_RECOVERY="${SCRIPT_DIR}/deploy_investment_hub_account_krw.sh"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-trade-badge-${STAMP}"
SRC="${WORK}/source"
mkdir -p "${SRC}"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }
need vercel
need python3
need tar
[ -f "${LEGACY_RECOVERY}" ] || fail "source recovery helper missing: ${LEGACY_RECOVERY}"

printf '%s\n' "==================================================" \
  "Kalman Investment Hub ${VERSION_TAG}" \
  "Header trade-state semantics correction" \
  "==================================================" \
  "Base deployment: ${BASE_DEPLOYMENT}"

vercel whoami >/dev/null
echo "[PASS] Vercel CLI authenticated"

echo "[1/6] Recover exact production source"
python3 - "${LEGACY_RECOVERY}" "${BASE_DEPLOYMENT}" "${TEAM_ID}" "${SRC}" <<'PY'
from pathlib import Path
import sys
helper, deployment, team_id, out_dir = sys.argv[1:5]
text = Path(helper).read_text(encoding="utf-8")
start_marker = 'python3 - "${GOOD_DEPLOYMENT}" "${TEAM_ID}" "${SRC}" <<\'PY\'\n'
end_marker = '\nPY\n\ntar -C "${SRC}"'
try:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
except ValueError as exc:
    raise SystemExit(f"[FAIL] could not locate source-recovery block: {exc}")
code = text[start:end]
old_argv = sys.argv
try:
    sys.argv = ["source_recovery", deployment, team_id, out_dir]
    exec(compile(code, "<kalman-source-recovery>", "exec"), {"__name__": "__main__"})
finally:
    sys.argv = old_argv
PY

api_count="$(find "${SRC}/api" -type f -name '*.js' | wc -l | tr -d ' ')"
[ "${api_count}" = "12" ] || fail "expected 12 API functions, got ${api_count}"
for f in index.html app.js style.css api/health.js api/account.js; do
  [ -f "${SRC}/${f}" ] || fail "missing recovered file: ${f}"
done
BACKUP="${HOME}/kalman-hub-trade-badge-base-${STAMP}.tar.gz"
tar -C "${SRC}" -czf "${BACKUP}" .
chmod 600 "${BACKUP}"
echo "[PASS] backup=${BACKUP}"

echo "[2/6] Patch header semantics only"
python3 - "${SRC}" "${VERSION_TAG}" <<'PY'
from pathlib import Path
import re, sys
root, version = Path(sys.argv[1]), sys.argv[2]
index_path = root / "index.html"
health_path = root / "api" / "health.js"
index = index_path.read_text(encoding="utf-8")
health = health_path.read_text(encoding="utf-8")
old = '<span class="pill warn">TRADE OFF</span>'
new = '<span id="headerTradeState" class="pill">WEB READ ONLY</span>'
if index.count(old) != 1:
    raise SystemExit(f"[FAIL] expected exactly one static TRADE OFF badge, got {index.count(old)}")
index = index.replace(old, new, 1)
index, n_index = re.subn(r'vNext\.7\.4\.\d+', version, index)
health, n_health = re.subn(r'vNext\.7\.4\.\d+', version, health)
if n_index < 1 or n_health < 1:
    raise SystemExit(f"[FAIL] version marker missing: index={n_index}, health={n_health}")
if 'TRADE OFF' in index or 'WEB READ ONLY' not in index:
    raise SystemExit('[FAIL] header badge patch did not apply cleanly')
index_path.write_text(index, encoding="utf-8")
health_path.write_text(health, encoding="utf-8")
print('[PASS] TRADE OFF -> WEB READ ONLY')
print('[PASS] no account/model/trading execution code modified')
PY

echo "[3/6] Link and build candidate"
mkdir -p "${SRC}/.vercel"
printf '{"projectId":"%s","orgId":"%s"}\n' "${PROJECT_ID}" "${TEAM_ID}" >"${SRC}/.vercel/project.json"
(
  cd "${SRC}"
  vercel deploy --dry --format=json --scope "${TEAM_SLUG}"
) >"${WORK}/dry-run.json"
[ -s "${WORK}/dry-run.json" ] || fail "empty Vercel dry-run output"

set +e
(
  cd "${SRC}"
  vercel deploy --prod --skip-domain --yes --scope "${TEAM_SLUG}"
) 2>&1 | tee "${WORK}/candidate-deploy.log"
rc=${PIPESTATUS[0]}
set -e
[ "${rc}" -eq 0 ] || fail "candidate deployment failed"
CANDIDATE="$(python3 - "${WORK}/candidate-deploy.log" <<'PY'
import re,sys
text=open(sys.argv[1], encoding='utf-8', errors='replace').read()
urls=re.findall(r'https://[A-Za-z0-9.-]+\.vercel\.app', text)
print(urls[-1] if urls else '')
PY
)"
[ -n "${CANDIDATE}" ] || fail "candidate URL not found"
echo "[PASS] candidate=${CANDIDATE}"

vcurl(){
  local path="$1" out="$2"
  vercel curl "${CANDIDATE}${path}" -sS >"${out}"
  [ -s "${out}" ] || fail "empty response: ${path}"
}

echo "[4/6] Candidate smoke tests"
vcurl "/api/health" "${WORK}/health.json"
vcurl "/api/account" "${WORK}/account.json"
vcurl "/api/dashboard?market=GLOBAL" "${WORK}/dashboard.json"
vcurl "/index.html" "${WORK}/index.html"
python3 - "${WORK}" "${VERSION_TAG}" <<'PY'
from pathlib import Path
import json,sys
root, version = Path(sys.argv[1]), sys.argv[2]
health=json.loads((root/'health.json').read_text())
account=json.loads((root/'account.json').read_text())
dashboard=json.loads((root/'dashboard.json').read_text())
index=(root/'index.html').read_text(encoding='utf-8', errors='replace')
assert health.get('trade_enabled') is False
assert health.get('account_trade_execution') is False
assert account.get('trade_execution') is False
assert account.get('status') == 'READY'
assert not dashboard.get('error')
assert 'WEB READ ONLY' in index
assert 'TRADE OFF' not in index
assert version in index
assert health.get('investment_hub_version') == version
print('[PASS] candidate web remains read-only')
print('[PASS] candidate account READY + dashboard healthy')
print('[PASS] candidate header = WEB READ ONLY')
PY

echo "[5/6] Promote candidate"
vercel promote "${CANDIDATE}" --yes --scope "${TEAM_SLUG}" >/dev/null
echo "[PASS] promoted"

echo "[6/6] Production verification"
for _ in $(seq 1 30); do
  set +e
  vercel curl "${PROD_URL}/api/health" -sS >"${WORK}/prod-health.json" 2>/dev/null
  r1=$?
  vercel curl "${PROD_URL}/api/account" -sS >"${WORK}/prod-account.json" 2>/dev/null
  r2=$?
  vercel curl "${PROD_URL}/index.html" -sS >"${WORK}/prod-index.html" 2>/dev/null
  r3=$?
  set -e
  if [ "$r1" -eq 0 ] && [ "$r2" -eq 0 ] && [ "$r3" -eq 0 ] && python3 - "${WORK}" "${VERSION_TAG}" <<'PY' >/dev/null 2>&1
from pathlib import Path
import json,sys
root, version = Path(sys.argv[1]), sys.argv[2]
h=json.loads((root/'prod-health.json').read_text())
a=json.loads((root/'prod-account.json').read_text())
i=(root/'prod-index.html').read_text(encoding='utf-8', errors='replace')
assert h.get('trade_enabled') is False
assert h.get('account_trade_execution') is False
assert a.get('trade_execution') is False
assert a.get('status') == 'READY'
assert h.get('investment_hub_version') == version
assert 'WEB READ ONLY' in i and 'TRADE OFF' not in i
PY
  then
    echo "[PASS] production verified"
    echo "DONE: ${PROD_URL}"
    echo "  header            = WEB READ ONLY"
    echo "  web trade_enabled = false"
    echo "  account execution = false"
    echo "  version           = ${VERSION_TAG}"
    exit 0
  fi
  sleep 2
done
fail "production verification failed after promotion"
