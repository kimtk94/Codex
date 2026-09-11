#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"

"$APP_ROOT/scripts/run_sa_collector.sh"
"$APP_ROOT/scripts/run_sa_us_btc_features.sh"
