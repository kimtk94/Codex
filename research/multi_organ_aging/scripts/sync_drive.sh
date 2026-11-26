#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "\${BASH_SOURCE[0]}")" && pwd)"

echo "[INFO] Compatibility wrapper -> 90_sync_drive.sh"
bash "$SCRIPT_DIR/90_sync_drive.sh"
exit $?
