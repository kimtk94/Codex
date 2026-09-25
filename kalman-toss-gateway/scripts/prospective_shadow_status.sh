#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"

"$PY" - "$ENV_FILE" <<'PY'
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(sys.argv[1], override=True)
except Exception:
    pass

env_file = Path(sys.argv[1])
state_db = Path(os.environ.get("TRADING_STATE_DB", "/opt/kalman/state/trading.sqlite3"))
candidate_id = os.environ.get(
    "PROSPECTIVE_SHADOW_CANDIDATE_ID",
    "LIVE_POLICY_NO_PROFIT_FLIP_V1",
)
enabled = os.environ.get("PROSPECTIVE_SHADOW_ENABLED", "false").lower() == "true"
activated_at = os.environ.get("PROSPECTIVE_SHADOW_ACTIVATED_AT")

out = {
    "candidate_id": candidate_id,
    "enabled": enabled,
    "activated_at": activated_at,
    "env_file": str(env_file),
    "state_db": str(state_db),
    "table_present": False,
    "summary": None,
    "recent": [],
    "broker_order_capable": False,
}

if state_db.is_file():
    with sqlite3.connect(state_db) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='prospective_shadow_position'
            """
        ).fetchone()
        if table:
            out["table_present"] = True
            row = conn.execute(
                """
                SELECT count(*) AS total,
                       sum(CASE WHEN state='OPEN' THEN 1 ELSE 0 END) AS open_count,
                       sum(CASE WHEN state='CLOSED' THEN 1 ELSE 0 END) AS closed_count,
                       min(seeded_at) AS first_seeded_at,
                       max(seeded_at) AS last_seeded_at,
                       sum(CASE WHEN live_policy_exit_observed_at IS NOT NULL THEN 1 ELSE 0 END)
                         AS live_reference_exits
                FROM prospective_shadow_position
                WHERE candidate_id=?
                """,
                (candidate_id,),
            ).fetchone()
            obs = conn.execute(
                """
                SELECT count(*) AS observations
                FROM prospective_shadow_observation
                WHERE candidate_id=?
                """,
                (candidate_id,),
            ).fetchone()
            out["summary"] = {
                "total": int(row["total"] or 0),
                "open": int(row["open_count"] or 0),
                "closed": int(row["closed_count"] or 0),
                "live_reference_exits": int(row["live_reference_exits"] or 0),
                "observations": int(obs["observations"] or 0),
                "first_seeded_at": row["first_seeded_at"],
                "last_seeded_at": row["last_seeded_at"],
            }
            rows = conn.execute(
                """
                SELECT candidate_id,live_position_id,symbol,state,seeded_at,
                       entry_average_price,last_observed_at,last_price_return,
                       exit_at,exit_reason,exit_return,
                       live_policy_exit_observed_at,
                       live_policy_exit_reference_reason,
                       live_policy_exit_reference_return,
                       live_state_last,live_exit_reason_last
                FROM prospective_shadow_position
                WHERE candidate_id=?
                ORDER BY seeded_at DESC LIMIT 10
                """,
                (candidate_id,),
            ).fetchall()
            out["recent"] = [dict(x) for x in rows]

print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
PY

RC=$?
echo
echo "status_rc=$RC"
echo "read_only=true"
exit "$RC"
