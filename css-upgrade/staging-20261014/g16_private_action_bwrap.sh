#!/usr/bin/env bash
# Private-server G16 regression launcher. Synthetic fixtures only.
# Never import the CSS module/collector or run CSS main().
set -euo pipefail

SERVER_BASE="/home/taehoon/services/novogene-css"
SOURCE="$SERVER_BASE/app/Novogene_Mail_CSS_DashBoard_server.py"
VENV="$SERVER_BASE/.venv"
EXPECTED_SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
RUN_SCRIPT="${1:-}"

[[ -n "$RUN_SCRIPT" && -f "$RUN_SCRIPT" && ! -L "$RUN_SCRIPT" ]] || { echo "G16_FAIL_INVALID_TEST_FILE"; exit 42; }
[[ -r "$SOURCE" && -x "$VENV/bin/python" && -d "$VENV/lib" ]] || { echo "G16_FAIL_MISSING_PRIVATE_INPUT"; exit 43; }
[[ "$(sha256sum "$SOURCE" | cut -d' ' -f1)" == "$EXPECTED_SHA" ]] || { echo "G16_FAIL_PRIVATE_SOURCE_CHANGED"; exit 44; }
command -v bwrap >/dev/null || { echo "G16_FAIL_BWRAP_NOT_INSTALLED"; exit 45; }
echo "G16_PRIVATE_ACTION_SOURCE_SHA_PASS"
echo "G16_PRIVATE_ACTION_FULL_MAIN_NOT_RUN"

# All private mounts are read-only. Home, database files, mailbox, credentials,
# backup directories, systemd and live Sheets are absent from this namespace.
# The only writable surface is disposable tmpfs; networking is unshared.
bwrap \
  --unshare-user --unshare-net --unshare-pid --unshare-ipc --unshare-uts \
  --new-session --die-with-parent \
  --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin \
  --dev /dev --proc /proc --tmpfs /tmp \
  --dir /private --dir /mock \
  --ro-bind "$VENV" /venv \
  --ro-bind "$SOURCE" /private/css.py \
  --ro-bind "$RUN_SCRIPT" /mock/test.py \
  --clearenv \
  --setenv G16_SYNTHETIC_ONLY 1 \
  --setenv HOME /tmp \
  --setenv PYTHONNOUSERSITE 1 \
  --setenv PYTHONDONTWRITEBYTECODE 1 \
  /venv/bin/python /mock/test.py --source /private/css.py

echo "G16_PRIVATE_ACTION_GENERATORS_ISOLATED_PASS"
echo "G16_NO_PRODUCTION_DB_SHEET_MAIL_CRM_WRITE"
echo "G12_FULL_MAIN_NOT_EXECUTED"
