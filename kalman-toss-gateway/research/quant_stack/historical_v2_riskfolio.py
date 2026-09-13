from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .portfolio_targets import load_sleeve_returns, portfolio_equity_from_targets, portfolio_metrics
from .riskfolio_benchmarks import RISKFOLIO_METHODS, build_riskfolio_targets


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def run(
    output_root: Path,
    *,
    lookback_days: int = 180,
    min_observations: int = 90,
    rebalance_frequency: str = "M",
) -> dict[str, Any]:
    status = _load_json(output_root / "historical_experiment_status.json")
    markets = [
        market
        for market in ("US", "KR", "BTC")
        if status.get("markets", {}).get(market, {}).get("status") == "READY"
    ]
    if len(markets) < 2:
        raise RuntimeError("Riskfolio comparison requires at least two READY markets")

    returns = load_sleeve_returns(output_root, markets)
    root = output_root / "analysis_v2" / "portfolio_benchmarks"
    root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for method in RISKFOLIO_METHODS:
        targets = build_riskfolio_targets(
            returns,
            method=method,
            lookback_days=lookback_days,
            min_observations=min_observations,
            rebalance_frequency=rebalance_frequency,
        )
        equity = portfolio_equity_from_targets(returns, targets)
        metrics = portfolio_metrics(equity)

        fallback_rows = targets.loc[
            targets["optimization_status"].astype(str).str.upper().eq("FALLBACK")
        ]
        fallback_rebalance_count = int(fallback_rows["effective_ts"].nunique())

        method_dir = root / method
        method_dir.mkdir(parents=True, exist_ok=True)
        targets.to_parquet(method_dir / "portfolio_target.parquet", index=False)
        equity.to_parquet(method_dir / "portfolio_equity.parquet", index=False)
        _write_json(method_dir / "portfolio_performance.json", metrics)

        rows.append(
            {
                "method": method,
                "source": "RISKFOLIO",
                "target_rows": int(len(targets)),
                "rebalance_count": int(targets["effective_ts"].nunique()),
                "fallback_rebalance_count": fallback_rebalance_count,
                **metrics,
            }
        )

    comparison = pd.DataFrame(rows)
    comparison.to_csv(root / "riskfolio_portfolio_comparison.csv", index=False)
    payload = {
        "status": "READY",
        "methods": list(RISKFOLIO_METHODS),
        "markets": markets,
        "lookback_days": lookback_days,
        "min_observations": min_observations,
        "rebalance_frequency": rebalance_frequency,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "rows": rows,
    }
    _write_json(root / "riskfolio_portfolio_summary.json", payload)
    return payload


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Riskfolio side of Kalman Historical V2 benchmark")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--lookback-days", type=int, default=180)
    p.add_argument("--min-observations", type=int, default=90)
    p.add_argument("--rebalance", choices=["M", "Q"], default="M")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    payload = run(
        Path(args.output_dir).expanduser(),
        lookback_days=args.lookback_days,
        min_observations=args.min_observations,
        rebalance_frequency=args.rebalance,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
