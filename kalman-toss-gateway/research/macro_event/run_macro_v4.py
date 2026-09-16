from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.quant_stack.historical_v3_return_regime import (
    MARKETS,
    run_equal_weight_portfolio,
    run_market_v3,
)
from research.macro_event.compare_v3_v4 import compare_market


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalman Historical V4 macro-event candidate"
    )
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--baseline-v3-root", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--code-sha", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    baseline_root = Path(args.baseline_v3_root).expanduser()
    output_root = Path(args.output_dir).expanduser()
    spec = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))

    status: dict[str, Any] = {
        "status": "READY",
        "version": spec["version"],
        "code_sha": args.code_sha,
        "markets": {},
        "common_window_v3_vs_v4": {},
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }

    for market in MARKETS:
        try:
            status["markets"][market] = run_market_v3(
                market=market,
                matrix_dir=matrix_dir,
                output_root=output_root,
                spec=spec,
                code_sha=args.code_sha,
            )
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    ready = [
        market
        for market, row in status["markets"].items()
        if row.get("status") == "READY"
    ]

    if len(ready) >= 2:
        try:
            status["portfolio"] = run_equal_weight_portfolio(output_root)
        except Exception as exc:
            status["status"] = "FAIL"
            status["portfolio"] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    for market in ready:
        try:
            status["common_window_v3_vs_v4"][market] = compare_market(
                market=market,
                v3_root=baseline_root,
                v4_root=output_root,
                matrix_dir=matrix_dir,
                spec=spec,
            )
        except Exception as exc:
            status["common_window_v3_vs_v4"][market] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    _write_json(output_root / "macro_v4_candidate_summary.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
