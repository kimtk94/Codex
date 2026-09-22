from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


EXPECTED_STRATEGIES = {
    "A_EQUAL_WEIGHT",
    "B_STATIC_MAX_SHARPE",
    "C_RISK_CAP_110",
}
CONFIRM_VALUE = "CONFIRM_SHADOW_RANKING_MIRROR"


def _load_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ranking snapshot must be an object")
    return payload


def validate_snapshot(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "kalman-shadow-portfolio-ranking-v2":
        raise RuntimeError("unexpected shadow ranking schema")
    if payload.get("status") != "READY":
        raise RuntimeError("shadow ranking status must be READY")

    invariants = payload.get("invariants") or {}
    required_false = (
        "entry_allowed_for_real_orders",
        "auto_trade_visible",
        "production_model_write",
        "strategy_signal_write",
        "dashboard_snapshot_write",
        "toss_execution",
        "live_execution",
        "trade_execution",
    )
    for key in required_false:
        if invariants.get(key) is not False:
            raise RuntimeError(f"invariant {key} must be false")
    if invariants.get("research_only") is not True:
        raise RuntimeError("research_only invariant must be true")

    rows = payload.get("forward_ranking")
    if not isinstance(rows, list) or len(rows) != 3:
        raise RuntimeError("forward_ranking must contain exactly three strategies")
    names = {str(row.get("strategy")) for row in rows}
    if names != EXPECTED_STRATEGIES:
        raise RuntimeError(f"unexpected strategies: {sorted(names)}")

    ready = [row for row in rows if row.get("status") == "READY"]
    tracking_status = str(payload.get("tracking_status") or "")
    if tracking_status == "RANKING_ACTIVE":
        ranks = sorted(row.get("forward_rank") for row in ready)
        if ready and ranks != list(range(len(ready))):
            raise RuntimeError(f"forward ranks are not contiguous: {ranks}")
        if any(row.get("rank_eligible") is not True for row in ready):
            raise RuntimeError("RANKING_ACTIVE requires rank_eligible=true for all READY rows")
    else:
        if any(row.get("forward_rank") is not None for row in ready):
            raise RuntimeError(
                "non-active ranking state must not expose forward_rank values"
            )


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def mirror_snapshot(
    payload: dict[str, Any],
    *,
    db_url: str,
) -> dict[str, Any]:
    as_of = payload["data_as_of"]
    seed_end = payload["seed_end"]
    source_version = str(payload.get("source_version") or "shadow_portfolio_ranking_v2")
    code_sha = str(payload.get("code_sha") or "unknown")

    sql = """
    INSERT INTO shadow_portfolio_snapshot (
      as_of, seed_end, status, source_version, code_sha, payload, updated_at
    )
    VALUES (%s,%s,'READY',%s,%s,%s,now())
    ON CONFLICT (as_of, source_version)
    DO UPDATE SET
      seed_end=EXCLUDED.seed_end,
      status=EXCLUDED.status,
      code_sha=EXCLUDED.code_sha,
      payload=EXCLUDED.payload,
      updated_at=now()
    RETURNING snapshot_id,as_of,source_version,updated_at
    """

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (as_of, seed_end, source_version, code_sha, Jsonb(payload)))
            row = cur.fetchone()
        conn.commit()

    return {
        "snapshot_id": str(row[0]),
        "as_of": row[1].isoformat(),
        "source_version": row[2],
        "updated_at": row[3].isoformat(),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mirror SHADOW A/B/C ranking to Neon")
    p.add_argument("--ranking-file", required=True)
    p.add_argument("--status-file", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)

    ranking_path = Path(args.ranking_file).expanduser()
    status_path = Path(args.status_file).expanduser()
    payload = _load_snapshot(ranking_path)
    validate_snapshot(payload)

    if args.dry_run:
        report = {
            "status": "VALIDATED",
            "read_only": True,
            "ranking_file": str(ranking_path),
            "data_as_of": payload.get("data_as_of"),
            "strategies": sorted(EXPECTED_STRATEGIES),
            "neon_write": False,
            "trade_execution": False,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_status(status_path, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0

    enabled = str(os.environ.get("KALMAN_SHADOW_RANKING_NEON_ENABLED") or "").strip().lower()
    confirm = str(os.environ.get("KALMAN_SHADOW_RANKING_NEON_CONFIRM") or "").strip()
    if enabled != "true":
        raise RuntimeError("KALMAN_SHADOW_RANKING_NEON_ENABLED must be true")
    if confirm != CONFIRM_VALUE:
        raise RuntimeError("KALMAN_SHADOW_RANKING_NEON_CONFIRM mismatch")

    db_url = os.environ.get("DATABASE_URL_WRITER")
    if not db_url:
        raise RuntimeError("DATABASE_URL_WRITER is missing")

    mirrored = mirror_snapshot(payload, db_url=db_url)
    report = {
        "status": "MIRRORED",
        "read_only_broker_calls": True,
        "ranking_file": str(ranking_path),
        "data_as_of": payload.get("data_as_of"),
        "strategies": sorted(EXPECTED_STRATEGIES),
        "neon_write": True,
        "neon_target": "shadow_portfolio_snapshot",
        "strategy_signal_write": False,
        "dashboard_snapshot_write": False,
        "trade_execution": False,
        "mirror": mirrored,
        "mirrored_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_status(status_path, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
