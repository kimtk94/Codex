#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"

printf '[1/3] Market Data V2\n'
"$APP_ROOT/scripts/run_market_data_v2.sh" "$@"

printf '[2/3] TA-Lib Features V2\n'
"$APP_ROOT/scripts/run_features_v2.sh"

printf '[3/3] Finviz point-in-time snapshot\n'
"$APP_ROOT/scripts/run_finviz_v2.sh"

printf 'MARKET_TOOLS_V2_COMPLETE\n'
