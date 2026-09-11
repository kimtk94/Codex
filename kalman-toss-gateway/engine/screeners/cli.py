from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .finviz_snapshot import (
    FinvizSettings,
    build_candidate_universe,
    fetch_views,
    merge_views,
    save_snapshot,
)
from engine.market_data.snapshot import atomic_json


def _bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _filters(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("KALMAN_FINVIZ_FILTERS_JSON must be a JSON object")
    return {str(k): str(v) for k, v in parsed.items()}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create point-in-time Finviz screener snapshot")
    p.add_argument("--output-dir")
    p.add_argument("--limit", type=int)
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def main() -> int:
    env_file = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")).expanduser()
    if env_file.exists():
        load_dotenv(env_file, override=True)

    args = parse_args()
    data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser()
    output_dir = Path(
        args.output_dir
        or os.environ.get(
            "KALMAN_FINVIZ_OUTPUT_DIR",
            str(data_root / "Market_Screeners" / "finviz"),
        )
    ).expanduser()

    enabled = args.force or _bool(os.environ.get("KALMAN_FINVIZ_ENABLED", "false"))
    if not enabled:
        status = {
            "status": "DISABLED",
            "point_in_time": True,
            "production_writes": False,
            "message": "Set KALMAN_FINVIZ_ENABLED=true or pass --force for a manual run.",
        }
        atomic_json(output_dir / "finviz_run_status.json", status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    settings = FinvizSettings(
        output_dir=output_dir,
        limit=args.limit or int(os.environ.get("KALMAN_FINVIZ_LIMIT", "500")),
        filters=_filters(os.environ.get("KALMAN_FINVIZ_FILTERS_JSON")),
        signal=os.environ.get("KALMAN_FINVIZ_SIGNAL", "").strip(),
        min_price=float(os.environ.get("KALMAN_FINVIZ_MIN_PRICE", "0")),
        min_market_cap=float(os.environ.get("KALMAN_FINVIZ_MIN_MARKET_CAP", "0")),
        min_volume=float(os.environ.get("KALMAN_FINVIZ_MIN_VOLUME", "0")),
    )

    try:
        views, snapshot_at = fetch_views(settings)
        merged = merge_views(views)
        candidates = build_candidate_universe(merged, settings)
        status = save_snapshot(
            views,
            merged,
            candidates,
            settings=settings,
            snapshot_at=snapshot_at,
        )
        print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        status = {
            "status": "FAIL",
            "point_in_time": True,
            "production_writes": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        atomic_json(output_dir / "finviz_run_status.json", status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
