#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
NY_NOW="${KALMAN_NY_NOW:-$(TZ=America/New_York date '+%u %H %M')}"
read -r NY_DOW NY_HOUR NY_MIN <<<"$NY_NOW"
NY_HOUR=$((10#$NY_HOUR))
NY_MIN=$((10#$NY_MIN))

# US market automation is keyed to America/New_York so EDT/EST transitions
# never require changing KST cron entries. Weekend/holiday fail-closed checks
# remain in the downstream market guard / broker calendar.
if (( NY_DOW < 1 || NY_DOW > 5 )); then
  exit 0
fi

case "$MODE" in
  cycle)
    if (( NY_MIN == 35 && NY_HOUR >= 9 && NY_HOUR <= 15 )); then
      exec "$APP_ROOT/scripts/run_us_cycle.sh"
    fi
    ;;
  watchdog)
    if (( NY_MIN == 50 && NY_HOUR >= 9 && NY_HOUR <= 15 )); then
      exec "$APP_ROOT/scripts/us_auto_watchdog.sh"
    fi
    ;;
  execution)
    if (( NY_MIN % 5 == 0 )); then
      if (( (NY_HOUR == 9 && NY_MIN >= 25) || (NY_HOUR >= 10 && NY_HOUR <= 15) )); then
        exec "$APP_ROOT/scripts/run_execution_watch.sh"
      fi
    fi
    ;;
  *)
    echo "usage: $0 {cycle|watchdog|execution}" >&2
    exit 2
    ;;
esac
