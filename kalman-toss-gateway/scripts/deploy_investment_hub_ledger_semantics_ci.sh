#!/usr/bin/env bash
set -euo pipefail

# Deploy a presentation-only correction for the US R5.1 Ledger.
# Model logic, Neon data, Toss account data, and trading gates are untouched.

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
PROJECT_NAME="${VERCEL_PROJECT_NAME:-kalman-investment-hub-v2}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"
BASE_DEPLOYMENT="${KALMAN_HUB_BASE_DEPLOYMENT:-dpl_99ZABqst9m2kpnphkYkLJ5gJ1RQs}"
VERSION_TAG="${KALMAN_HUB_VERSION_TAG:-vNext.7.4.16}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY_RECOVERY="${SCRIPT_DIR}/deploy_investment_hub_account_krw.sh"
PATCH_JS="${SCRIPT_DIR}/ledger_semantics_patch.js"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-ledger-semantics-${STAMP}"
SRC="${WORK}/source"
mkdir -p "${SRC}"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }

need vercel
need python3
need curl
need tar
[ -f "${LEGACY_RECOVERY}" ] || fail "source recovery helper missing: ${LEGACY_RECOVERY}"
[ -f "${PATCH_JS}" ] || fail "UI patch missing: ${PATCH_JS}"

echo "=================================================="
echo "Kalman Investment Hub ${VERSION_TAG}"
echo "US Ledger semantics correction"
echo "=================================================="
echo "Base deployment: ${BASE_DEPLOYMENT}"
echo

echo "[0/7] Authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel CLI authenticated"

echo
echo "[1/7] Recover exact audited production source"
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
BACKUP="${KALMAN_HUB_BACKUP_DIR:-${HOME}}/kalman-hub-ledger-semantics-base-${STAMP}.tar.gz"
tar -C "${SRC}" -czf "${BACKUP}" .
chmod 600 "${BACKUP}"
echo "[PASS] exact source recovered; backup=${BACKUP}"

echo
echo "[2/7] Apply presentation-only patch"
python3 - "${SRC}" "${PATCH_JS}" "${VERSION_TAG}" <<'PY'
from pathlib import Path
import re
import sys

root, patch_file, version = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
app_path = root / "app.js"
index_path = root / "index.html"
health_path = root / "api" / "health.js"

app = app_path.read_text(encoding="utf-8")
index = index_path.read_text(encoding="utf-8")
health = health_path.read_text(encoding="utf-8")
patch = patch_file.read_text(encoding="utf-8").strip()

marker = "KALMAN_LEDGER_SEMANTICS_V1"
if marker in app:
    raise SystemExit("[FAIL] base already contains Ledger semantics patch")

# Do not touch APIs, model outputs, database queries, or account calculations.
app = app.rstrip() + "\n\n" + patch + "\n"

for old in ("vNext.7.4.15", "vNext.7.4.14"):
    index = index.replace(old, version)
    app = app.replace(old, version)
    health = health.replace(old, version)

checks = [
    marker,
    '"Shadow Entry"',
    '"Price Return"',
    '"Gross Strategy Return"',
    '"Net Strategy Return"',
    '"Broker Avg. Price"',
    "10bp",
]
missing = [x for x in checks if x not in app]
if missing:
    raise SystemExit(f"[FAIL] patch checks missing: {missing}")

for pat in (
    r"\btrade_execution\s*=\s*true\b",
    r"\btradeEnabled\s*=\s*true\b",
    r"\bAUTO_TRADE\s*=\s*true\b",
):
    if re.search(pat, patch, re.I):
        raise SystemExit(f"[FAIL] unsafe patch token: {pat}")

app_path.write_text(app, encoding="utf-8")
index_path.write_text(index, encoding="utf-8")
health_path.write_text(health, encoding="utf-8")
print("[PASS] Ledger labels corrected")
print("[PASS] account/model/trading code not modified")
PY

if command -v node >/dev/null 2>&1; then
  node --check "${SRC}/app.js" >/dev/null
  echo "[PASS] app.js syntax"
fi

echo
echo "[3/7] Link source and verify deployment manifest"
mkdir -p "${SRC}/.vercel"
printf '{"projectId":"%s","orgId":"%s"}\n' "${PROJECT_ID}" "${TEAM_ID}" >"${SRC}/.vercel/project.json"
(
  cd "${SRC}"
  vercel deploy --dry --format=json --scope "${TEAM_SLUG}"
) >"${WORK}/dry-run.json"
[ -s "${WORK}/dry-run.json" ] || fail "empty Vercel dry-run output"
echo "[PASS] Vercel dry-run"

echo
echo "[4/7] Build candidate without production-domain assignment"
set +e
(
  cd "${SRC}"
  vercel deploy --prod --skip-domain --yes --scope "${TEAM_SLUG}"
) 2>&1 | tee "${WORK}/candidate-deploy.log"
rc=${PIPESTATUS[0]}
set -e
[ "${rc}" -eq 0 ] || fail "candidate deployment failed"

CANDIDATE="$(
python3 - "${WORK}/candidate-deploy.log" <<'PY'
import re,sys
text=open(sys.argv[1], encoding="utf-8", errors="replace").read()
urls=re.findall(r"https://[A-Za-z0-9.-]+\.vercel\.app", text)
print(urls[-1] if urls else "")
PY
)"
[ -n "${CANDIDATE}" ] || fail "candidate URL not found"
echo "[PASS] candidate=${CANDIDATE}"

echo
echo "[5/7] Candidate smoke tests"
vcurl(){
  local path="$1" out="$2"
  vercel curl "${CANDIDATE}${path}" -sS >"${out}"
  [ -s "${out}" ] || fail "empty response: ${path}"
}
vcurl "/api/health" "${WORK}/health.json"
vcurl "/api/account" "${WORK}/account.json"
vcurl "/api/dashboard?market=GLOBAL" "${WORK}/dashboard.json"
vcurl "/app.js" "${WORK}/app.js"

python3 - "${WORK}" "${VERSION_TAG}" <<'PY'
from pathlib import Path
import json,sys
root, version = Path(sys.argv[1]), sys.argv[2]

health=json.loads((root/"health.json").read_text())
account=json.loads((root/"account.json").read_text())
dashboard=json.loads((root/"dashboard.json").read_text())
app=(root/"app.js").read_text(encoding="utf-8",errors="replace")

assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert account.get("trade_execution") is False
assert account.get("status") == "READY"
assert not dashboard.get("error")
assert "KALMAN_LEDGER_SEMANTICS_V1" in app
for token in ("Shadow Entry","Price Return","Net Strategy Return","Broker Avg. Price"):
    assert token in app, token
print("[PASS] APIs healthy; trading remains disabled")
print("[PASS] Ledger semantics patch served by candidate")
PY

echo
echo "[6/7] Promote candidate"
vercel promote "${CANDIDATE}" --yes --scope "${TEAM_SLUG}" >/dev/null
echo "[PASS] promoted"

echo
echo "[7/7] Production verification"
vercel curl "${PROD_URL}/api/health" -sS >"${WORK}/prod-health.json"
vercel curl "${PROD_URL}/app.js" -sS >"${WORK}/prod-app.js"
python3 - "${WORK}" <<'PY'
from pathlib import Path
import json,sys
root=Path(sys.argv[1])
health=json.loads((root/"prod-health.json").read_text())
app=(root/"prod-app.js").read_text(encoding="utf-8",errors="replace")
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert "KALMAN_LEDGER_SEMANTICS_V1" in app
print("[PASS] production patch visible")
print("[PASS] production trading gates remain disabled")
PY

echo
echo "DONE: ${PROD_URL}"
echo "  Ledger entry_price        = Shadow Entry"
echo "  raw_return                = Price Return"
echo "  position_weight           = Weight"
echo "  gross_weighted_return     = Gross Strategy Return"
echo "  return_pct/net10_return   = Net Strategy Return"
echo "  Toss averagePurchasePrice = Broker Avg. Price"
