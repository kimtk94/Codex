#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

MODE="${1:-show}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
CANDIDATE_ID="LIVE_POLICY_NO_PROFIT_FLIP_V1"

if [[ "$MODE" != "show" && "$MODE" != "enable" && "$MODE" != "disable" ]]; then
  echo "usage: $0 [show|enable|disable]"
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[FAIL] env file missing: $ENV_FILE"
  exit 2
fi

if [[ "$MODE" == "show" ]]; then
  echo "===== PROSPECTIVE SHADOW ENV ====="
  grep -E '^(PROSPECTIVE_SHADOW_ENABLED|PROSPECTIVE_SHADOW_CANDIDATE_ID|PROSPECTIVE_SHADOW_ACTIVATED_AT)=' "$ENV_FILE" || true
  echo
  echo "frozen_candidate=$CANDIDATE_ID"
  echo "profit_flip=false"
  echo "stop_loss=-0.03"
  echo "take_profit=0.20"
  echo "model_rotation=false"
  echo "target_exit_buckets=4"
  exit 0
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$ENV_FILE.bak.prospective-shadow.$STAMP"
cp -a "$ENV_FILE" "$BACKUP"
BACKUP_RC=$?
if [[ $BACKUP_RC -ne 0 ]]; then
  echo "[FAIL] env backup failed rc=$BACKUP_RC"
  exit "$BACKUP_RC"
fi

ACTIVATED_AT=""
if [[ "$MODE" == "enable" ]]; then
  ACTIVATED_AT="${PROSPECTIVE_SHADOW_ACTIVATED_AT_OVERRIDE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
fi

"$PY" - "$ENV_FILE" "$MODE" "$CANDIDATE_ID" "$ACTIVATED_AT" <<'PY'
from pathlib import Path
import os
import sys
import tempfile

path = Path(sys.argv[1])
mode = sys.argv[2]
candidate_id = sys.argv[3]
activated_at = sys.argv[4]

updates = {
    "PROSPECTIVE_SHADOW_ENABLED": "true" if mode == "enable" else "false",
    "PROSPECTIVE_SHADOW_CANDIDATE_ID": candidate_id,
}
if mode == "enable":
    updates["PROSPECTIVE_SHADOW_ACTIVATED_AT"] = activated_at

lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

mode_bits = path.stat().st_mode & 0o777
fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
os.close(fd)
tmp = Path(tmp_name)
try:
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(tmp, mode_bits)
    os.replace(tmp, path)
finally:
    if tmp.exists():
        tmp.unlink()
PY
WRITE_RC=$?

if [[ $WRITE_RC -ne 0 ]]; then
  echo "[FAIL] env update failed rc=$WRITE_RC"
  echo "backup=$BACKUP"
  exit "$WRITE_RC"
fi

echo "===== PROSPECTIVE SHADOW UPDATED ====="
echo "mode=$MODE"
echo "candidate_id=$CANDIDATE_ID"
if [[ "$MODE" == "enable" ]]; then
  echo "activated_at=$ACTIVATED_AT"
fi
echo "backup=$BACKUP"
echo
grep -E '^(PROSPECTIVE_SHADOW_ENABLED|PROSPECTIVE_SHADOW_CANDIDATE_ID|PROSPECTIVE_SHADOW_ACTIVATED_AT)=' "$ENV_FILE" || true

exit 0
