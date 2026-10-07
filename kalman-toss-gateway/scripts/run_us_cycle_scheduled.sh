#!/usr/bin/env bash
set -uo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ET_HM="$(TZ=America/New_York date +%H:%M)"

case "$ET_HM" in
  09:35|10:35|11:35|12:35|13:35|14:35)
    echo "US_CYCLE_SCHEDULE_ADMIT_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) et_time=$ET_HM"
    exec bash "$APP_ROOT/scripts/run_us_cycle.sh"
    ;;
  *)
    echo "US_CYCLE_SCHEDULE_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=OUTSIDE_R51_ET_WINDOW et_time=$ET_HM"
    exit 0
    ;;
esac
