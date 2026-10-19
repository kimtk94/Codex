#!/usr/bin/env bash
# Run only after reviewing third-party npm package and preflight.
set -u
if [ "$(id -u)" -eq 0 ]; then echo 'BLOCKED: root execution'; exit 2; fi
case "$(pwd -P)" in /opt/kalman*|/srv/kalman*) echo 'BLOCKED: LIVE workspace'; exit 2;; esac
BASE="$HOME/rea-pilot"
mkdir -p "$BASE/npm-cache" "$BASE/reports"
export npm_config_cache="$BASE/npm-cache"
export npm_config_update_notifier=false
npx --yes rea-agents@latest doctor > "$BASE/reports/doctor.log" 2>&1
status=$?
printf 'doctor_exit=%s\nreport=%s\n' "$status" "$BASE/reports/doctor.log"
tail -n 30 "$BASE/reports/doctor.log"
exit "$status"
