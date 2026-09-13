#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"

# Compatibility wrapper.
# The canonical scheduled flow lives in run_shadow_bakeoff_daily.sh because it
# owns the historical integrated source freshness gate.
exec /bin/bash "$APP_ROOT/scripts/run_shadow_bakeoff_daily.sh" "$@"
