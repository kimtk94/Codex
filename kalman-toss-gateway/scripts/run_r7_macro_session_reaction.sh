#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
EVENTS="${R7_MACRO_EVENTS:-/opt/kalman/state/r7_macro_free/events.json}"
QQQ="${R7_QQQ_1H:-/mnt/gdrive/US_ETF/directional_research/canonical_history_v1/qqq_context/history_1h/QQQ_1h_gap_aware.parquet}"
OUT="${R7_MACRO_REACTION_OUT:-/opt/kalman/state/r7_macro_reaction}"

echo "===== R7 FREE SESSION REACTION ====="
echo "events=$EVENTS"
echo "qqq=$QQQ"
echo "output=$OUT"
echo "contract=QQQ_SESSION_REACTION_1H"
echo "intraday_us2y=false"

sudo_test=0
[ -f "$EVENTS" ] || { echo "[FAIL] events missing: $EVENTS"; sudo_test=1; }
[ -f "$QQQ" ] || { echo "[FAIL] QQQ parquet missing: $QQQ"; sudo_test=1; }
[ "$sudo_test" -eq 0 ] || { return 2 2>/dev/null || exit 2; }

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r7_macro_session_reaction.py" \
  --events "$EVENTS" \
  --qqq "$QQQ" \
  --output-dir "$OUT"
