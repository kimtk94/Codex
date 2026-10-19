#!/usr/bin/env bash
# Private-server synthetic SIF regression inside rootless Bubblewrap.
# No production CSS main(), no collector imports, no network, no live DB/Sheets.
set -euo pipefail

BASE="/home/taehoon/services/novogene-css"
SOURCE="$BASE/app/Novogene_Mail_CSS_DashBoard_server.py"
VENV="$BASE/.venv"
EXPECTED="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
REMOTE_DIR="${1:-}"
SCRIPT="${2:-}"
[[ "$REMOTE_DIR" =~ ^/tmp/css-sif-bwrap-[0-9]+-[0-9]+$ ]] || { echo "G16_SIF_DENY_REMOTE_DIR"; exit 40; }
[[ "$SCRIPT" == "large_sif_workflow_regression.py" || "$SCRIPT" == "manual_mail_overlap_regression.py" || "$SCRIPT" == "g12_sif_action_handoff.py" ]] || { echo "G16_SIF_DENY_SCRIPT"; exit 41; }
[[ -f "$REMOTE_DIR/$SCRIPT" && ! -L "$REMOTE_DIR/$SCRIPT" ]] || { echo "G16_SIF_MISSING_SCRIPT"; exit 42; }
[[ -r "$SOURCE" && -x "$VENV/bin/python" && -d "$VENV/lib" ]] || { echo "G16_SIF_MISSING_READONLY_INPUT"; exit 43; }
[[ "$(sha256sum "$SOURCE" | cut -d' ' -f1)" == "$EXPECTED" ]] || { echo "G16_SIF_SOURCE_CHANGED"; exit 44; }
command -v bwrap >/dev/null || { echo "G16_SIF_MISSING_BWRAP"; exit 45; }
for p in   novogene_sif_history_candidate.patch   novogene_sif_manual_override_collision.patch   novogene_sif_portfolio_visibility.patch   novogene_sif_independent_actions.patch   novogene_sif_atomic_auto_skip.patch   novogene_css_hold_replay_guard.patch   novogene_css_one_shot_receipts.patch   novogene_css_snapshot_conflict_guard.patch; do
  [[ -f "$REMOTE_DIR/$p" && ! -L "$REMOTE_DIR/$p" ]] || { echo "G16_SIF_MISSING_PATCH"; exit 46; }
done
echo "G16_SIF_SHA_PINNED_SOURCE_PASS"
echo "G16_SIF_PATCHES_STAGING_ONLY"

# Proprietary source is read-only in a private mount. A disposable tmpfs
# contains both temporary source patch copies and the synthetic SQLite DB.
# No host-home, actual mail DB, auth credentials or service paths are mounted.
bwrap   --unshare-user --unshare-net --unshare-pid --unshare-ipc --unshare-uts   --new-session --die-with-parent   --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin   --dev /dev --proc /proc --tmpfs /tmp   --dir /private --dir /mock   --ro-bind "$VENV" /venv   --ro-bind "$SOURCE" /private/css.py   --ro-bind "$REMOTE_DIR" /mock   --clearenv --setenv G16_SYNTHETIC_ONLY 1   --setenv HOME /tmp --setenv TMPDIR /tmp   --setenv PYTHONNOUSERSITE 1 --setenv PYTHONDONTWRITEBYTECODE 1   /venv/bin/python "/mock/$SCRIPT"     --source /private/css.py     --patch /mock/novogene_sif_history_candidate.patch     --patch /mock/novogene_sif_manual_override_collision.patch     --patch /mock/novogene_sif_portfolio_visibility.patch     --patch /mock/novogene_sif_independent_actions.patch     --patch /mock/novogene_sif_atomic_auto_skip.patch     --patch /mock/novogene_css_hold_replay_guard.patch     --patch /mock/novogene_css_one_shot_receipts.patch     --patch /mock/novogene_css_snapshot_conflict_guard.patch

echo "G16_PRIVATE_REAL_SIF_REGRESSION_ISOLATED_PASS"
echo "G16_NO_LIVE_DB_SHEET_MAIL_CRM_WRITES"
echo "G12_FULL_MAIN_NOT_EXECUTED"
