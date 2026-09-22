#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
EVENTS="${R9_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}"

if [ -z "${SEC_CONTACT_EMAIL:-}" ]; then
  echo "[FAIL] SEC_CONTACT_EMAIL is required" >&2
  return 2 2>/dev/null || exit 2
fi

UA="${SEC_USER_AGENT:-Kalman Research $SEC_CONTACT_EMAIL}"

readarray -t PROBE < <("$PY" - "$EVENTS" <<'PY'
import json,sys
from pathlib import Path
rows=json.loads(Path(sys.argv[1]).read_text())
e=next(
    x for x in rows
    if x.get("primary_url")
    and any(i in {"1.01","2.01","2.02","2.03","3.01","3.02","2.05","2.06","5.02","7.01","8.01"} for i in (x.get("items") or []))
)
print(e["symbol"])
print(e["cik"])
print(e["primary_url"])
PY
)

SYM="${PROBE[0]}"
CIK="${PROBE[1]}"
ARCHIVE_URL="${PROBE[2]}"
SUB_URL="https://data.sec.gov/submissions/CIK${CIK}.json"

echo "===== SEC ACCESS PROBE ====="
echo "symbol=$SYM"
echo "cik=$CIK"
echo "archive_url=$ARCHIVE_URL"
echo

probe_url() {
  local label="$1"
  local url="$2"
  local host="$3"
  local tmp
  tmp="$(mktemp)"

  echo "===== $label ====="
  curl -sS -D - -o "$tmp" \
    --max-time 20 \
    -H "User-Agent: $UA" \
    -H "From: $SEC_CONTACT_EMAIL" \
    -H "Accept-Encoding: gzip, deflate" \
    -H "Host: $host" \
    "$url" \
    | sed -n '1,25p'

  rc=$?
  echo "curl_rc=$rc"
  echo "--- body first 1200 bytes ---"
  head -c 1200 "$tmp" | tr '\n' ' '
  echo
  echo
  rm -f "$tmp"
}

probe_url "DATA.SEC.GOV" "$SUB_URL" "data.sec.gov"
sleep 2
probe_url "WWW.SEC.GOV ARCHIVE" "$ARCHIVE_URL" "www.sec.gov"

echo "===== PUBLIC IP ====="
curl -sS --max-time 10 https://api.ipify.org || true
echo
