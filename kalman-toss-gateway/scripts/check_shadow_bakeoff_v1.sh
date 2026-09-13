#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$VENV/bin/python"

[ -x "$PY" ] || { echo "[FAIL] research python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }

export KALMAN_ENV_FILE="$ENV_FILE"

DATA_ROOT="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

MODEL_ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
OUTPUT_ROOT="${KALMAN_SHADOW_BAKEOFF_OUTPUT_DIR:-$MODEL_ROOT/shadow_bakeoff/v1}"

SCHEDULER="$OUTPUT_ROOT/latest/scheduler_status.json"
SOURCE="$OUTPUT_ROOT/latest/source_freshness.json"
BAKEOFF="$OUTPUT_ROOT/latest/bakeoff_status.json"

"$PY" - "$SCHEDULER" "$SOURCE" "$BAKEOFF" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


scheduler_path, source_path, bakeoff_path = map(Path, sys.argv[1:4])
scheduler = load(scheduler_path)
source = load(source_path)
bakeoff = load(bakeoff_path)

print("=" * 76)
print("KALMAN FORWARD SHADOW BAKE-OFF V1 HEALTH")
print("=" * 76)

if scheduler is None:
    print("scheduler : MISSING")
else:
    print("scheduler :", scheduler.get("status"))
    print("message   :", scheduler.get("message"))
    print("updated   :", scheduler.get("updated_at"))

if source is None:
    print("source    : MISSING")
else:
    print("source    :", source.get("status"))
    print("seed_end  :", source.get("seed_end"))
    print("anchors   :", source.get("anchor_max"))
    print("features  :", source.get("feature_max_available_time"))

if bakeoff is None:
    print("bakeoff   : MISSING")
    raise SystemExit(2)

print("bakeoff   :", bakeoff.get("status"))
print("tracking  :", bakeoff.get("tracking_status"))
print("seed_end  :", bakeoff.get("seed_end"))
print("latest    :", bakeoff.get("latest_as_of"))
print("post_seed :", bakeoff.get("post_seed_return_rows"))

signals = bakeoff.get("signal_status") or {}
for market in ("US", "KR", "BTC"):
    row = signals.get(market) or {}
    print(
        f"{market:<3} signal : "
        f"{row.get('signal')} | as_of={row.get('as_of')} | "
        f"model={row.get('model_family')}"
    )

print()
print("A/B/C")
for row in bakeoff.get("forward_ranking") or []:
    print(
        f"- {row.get('strategy')}: "
        f"{row.get('status')} "
        f"rank={row.get('forward_rank')} "
        f"target={row.get('latest_target')}"
    )

inv = bakeoff.get("invariants") or {}
checks = {
    "file_only": inv.get("file_only") is True,
    "production_write=false": inv.get("production_write") is False,
    "neon_write=false": inv.get("neon_write") is False,
    "toss_execution=false": inv.get("toss_execution") is False,
    "live_execution=false": inv.get("live_execution") is False,
    "auto_trade_visible=false": inv.get("auto_trade_visible") is False,
    "dashboard_snapshot_created=false": inv.get("dashboard_snapshot_created") is False,
}
print()
print("SAFETY")
for key, passed in checks.items():
    print(f"- {key}: {'PASS' if passed else 'FAIL'}")

if not all(checks.values()):
    raise SystemExit(3)

tracking = str(bakeoff.get("tracking_status") or "")
if tracking == "TRACKING":
    print("\nHEALTH=TRACKING")
    raise SystemExit(0)
if tracking == "WAITING_FOR_FORWARD_DATA":
    print("\nHEALTH=WAITING_FOR_FORWARD_DATA")
    raise SystemExit(0)

print(f"\nHEALTH={tracking or 'UNKNOWN'}")
raise SystemExit(0)
PY
