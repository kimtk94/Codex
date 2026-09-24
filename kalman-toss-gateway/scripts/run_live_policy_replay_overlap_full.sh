#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive/US_ETF}"
BOUNDARY_FILE="${LIVE_POLICY_REPLAY_BOUNDARY_FILE:-$ROOT/model_lab_v1/results/live_policy_replay_v1/boats_history_boundary.json}"
OUT_DIR="${LIVE_POLICY_REPLAY_FULL_OUTPUT_DIR:-$ROOT/model_lab_v1/results/live_policy_replay_v1_2025_full}"
END_DATE="${LIVE_POLICY_REPLAY_OVERLAP_END:-2025-12-31}"
N_BOOT="${LIVE_POLICY_REPLAY_FULL_N_BOOT:-10000}"

export KALMAN_ENV_FILE="$ENV_FILE"

echo "===================================================="
echo "LIVE POLICY REPLAY — 2025 FULL STATISTICAL RUN"
echo "===================================================="
echo "app_root=$APP_ROOT"
echo "boundary_file=$BOUNDARY_FILE"
echo "output_dir=$OUT_DIR"
echo "end=$END_DATE"
echo "n_boot=$N_BOOT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[FAIL] env file missing: $ENV_FILE"
  exit 2
fi

if [[ ! -f "$BOUNDARY_FILE" ]]; then
  echo "[FAIL] boundary file missing: $BOUNDARY_FILE"
  exit 2
fi

if ! mountpoint -q /mnt/gdrive; then
  echo "[FAIL] /mnt/gdrive is not mounted"
  exit 3
fi

BOUNDARY="$("$PY" - "$BOUNDARY_FILE" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
x = json.loads(p.read_text(encoding="utf-8"))

if not bool(x.get("baseline_overlaps_boats_history")):
    raise SystemExit(3)

value = x.get("first_common_candidate_utc")
if value is None:
    raise SystemExit(4)

print(str(value))
PY
)"
BOUNDARY_RC=$?

if [[ $BOUNDARY_RC -ne 0 || -z "$BOUNDARY" ]]; then
  echo "[FAIL] no valid overlap boundary found"
  echo "boundary_rc=$BOUNDARY_RC"
  exit 4
fi

mkdir -p "$OUT_DIR"
MKDIR_RC=$?
if [[ $MKDIR_RC -ne 0 ]]; then
  echo "[FAIL] cannot create output dir: $OUT_DIR"
  exit "$MKDIR_RC"
fi

cd "$APP_ROOT"
CD_RC=$?
if [[ $CD_RC -ne 0 ]]; then
  echo "[FAIL] cannot cd to app_root=$APP_ROOT"
  exit "$CD_RC"
fi

echo
echo "===== RESOLVED STUDY WINDOW ====="
echo "start=$BOUNDARY"
echo "end=$END_DATE"

echo
echo "===== FULL REPLAY ====="
bash scripts/run_live_policy_replay.sh   --start "$BOUNDARY"   --end "$END_DATE"   --feed iex   --overnight-feed boats   --output-dir "$OUT_DIR"   --event-audit changes   --n-boot "$N_BOOT"

RUN_RC=$?

echo
echo "===== FULL REPLAY COMMAND RESULT ====="
echo "run_rc=$RUN_RC"

STATUS="$OUT_DIR/status.json"
DECISION="$OUT_DIR/live_policy_replay_decision.json"

if [[ ! -f "$STATUS" ]]; then
  echo "[FAIL] status file missing: $STATUS"
  exit 5
fi

echo
echo "===== STATUS ====="
cat "$STATUS"

if [[ $RUN_RC -ne 0 ]]; then
  echo "[FAIL] full replay failed rc=$RUN_RC"
  exit "$RUN_RC"
fi

if [[ ! -f "$DECISION" ]]; then
  echo "[FAIL] decision file missing: $DECISION"
  exit 6
fi

echo
echo "===== DECISION SUMMARY ====="
"$PY" - "$DECISION" <<'PY'
import json
import sys
from pathlib import Path

x = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
coverage = x.get("coverage") or {}
baseline = x.get("baseline") or {}
candidate = x.get("candidate_metrics") or {}
boot = x.get("paired_bootstrap") or {}
recon = x.get("reconciliation") or {}

print(f"research_survivor={x.get('research_survivor')}")
print(f"promotion_recommendation={x.get('promotion_recommendation')}")
print(f"delta_log_growth_vs_fixed4={x.get('delta_log_growth_vs_fixed4')}")
print(f"mdd_delta_vs_fixed4={x.get('mdd_delta_vs_fixed4')}")
print(f"positive_folds={x.get('positive_folds')}/{x.get('fold_count')}")
print(f"triggered_exits={x.get('triggered_exits')}")
print(f"trigger_rate_ready={x.get('trigger_rate_ready')}")
print(f"ready_ratio={coverage.get('ready_ratio')}")
print(f"median_watch_coverage={coverage.get('median_watch_coverage')}")
print(f"median_position_watch_coverage={coverage.get('median_position_watch_coverage')}")
print(f"median_execution_watch_coverage={coverage.get('median_execution_watch_coverage')}")
print(f"median_regular_exec_coverage={coverage.get('median_regular_exec_coverage')}")
print(f"median_overnight_watch_coverage={coverage.get('median_overnight_watch_coverage')}")
print(f"bootstrap_ci95_low={boot.get('ci95_low')}")
print(f"bootstrap_ci95_high={boot.get('ci95_high')}")
print(f"bootstrap_p_one_sided={boot.get('p_one_sided')}")
print(f"baseline_log_growth={baseline.get('log_growth')}")
print(f"candidate_log_growth={candidate.get('log_growth')}")
print(f"baseline_mdd={baseline.get('mdd')}")
print(f"candidate_mdd={candidate.get('mdd')}")
print(f"reconciliation_median_abs_net_diff={recon.get('median_abs_net_diff')}")
print(f"reconciliation_corr={recon.get('corr')}")

print()
print("EXIT_REASON_COUNTS")
for key, value in (x.get("exit_reason_counts") or {}).items():
    print(f"{key}={value}")

print()
print("ATTRIBUTION")
for row in x.get("reason_attribution") or []:
    print(
        f"{row.get('exit_reason')}: "
        f"trades={row.get('trades')} "
        f"delta_net_sum={row.get('delta_net_sum')} "
        f"mean_delta={row.get('mean_delta_per_trade')} "
        f"positive_delta_rate={row.get('positive_delta_rate')}"
    )
PY
SUMMARY_RC=$?

echo
echo "===== ARTIFACTS ====="
echo "status=$STATUS"
echo "decision=$DECISION"
echo "trade_audit=$OUT_DIR/live_policy_replay_trade_audit.parquet"
echo "event_audit=$OUT_DIR/live_policy_replay_event_audit.parquet"
echo "fold_summary=$OUT_DIR/live_policy_replay_fold_summary.csv"
echo "reason_summary=$OUT_DIR/live_policy_replay_reason_summary.csv"
echo "attribution=$OUT_DIR/live_policy_replay_attribution.csv"
echo "summary_rc=$SUMMARY_RC"

exit "$SUMMARY_RC"
