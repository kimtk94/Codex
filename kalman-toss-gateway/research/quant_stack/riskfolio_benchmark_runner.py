from __future__ import annotations

import argparse
import json
from pathlib import Path

from .riskfolio_benchmarks import RISKFOLIO_METHODS, run_riskfolio_benchmarks


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run isolated Riskfolio-Lib benchmarks on Kalman portfolio sleeves"
    )
    p.add_argument("--output-dir", required=True)
    p.add_argument("--market", action="append", choices=["US", "KR", "BTC"])
    p.add_argument(
        "--method",
        action="append",
        choices=list(RISKFOLIO_METHODS),
    )
    p.add_argument("--lookback-days", type=int, default=180)
    p.add_argument("--min-observations", type=int, default=90)
    p.add_argument("--rebalance", choices=["M", "Q"], default="M")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.output_dir).expanduser()
    status_path = root / "historical_experiment_status.json"
    if not status_path.exists():
        raise FileNotFoundError(status_path)

    status = json.loads(status_path.read_text(encoding="utf-8"))
    ready_markets = [
        market
        for market, item in status.get("markets", {}).items()
        if item.get("status") == "READY"
    ]
    requested = args.market or ready_markets
    markets = [market for market in requested if market in ready_markets]

    if len(markets) < 2:
        raise RuntimeError("Riskfolio benchmark requires at least two READY markets")

    methods = tuple(args.method or list(RISKFOLIO_METHODS))
    result = run_riskfolio_benchmarks(
        root,
        markets=markets,
        methods=methods,
        lookback_days=args.lookback_days,
        min_observations=args.min_observations,
        rebalance_frequency=args.rebalance,
    )

    summary = {
        "status": "READY",
        "research_only": True,
        "live_execution": False,
        "neon_write": False,
        "toss_execution": False,
        "markets": markets,
        "methods": list(methods),
        "comparison_rows": int(len(result.comparison)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
