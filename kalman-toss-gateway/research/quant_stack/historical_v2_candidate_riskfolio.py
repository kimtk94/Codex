from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .portfolio_targets import portfolio_equity_from_targets, portfolio_metrics
from .riskfolio_benchmarks import RISKFOLIO_METHODS, build_riskfolio_targets


MARKETS = ("US", "KR", "BTC")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def load_candidate_returns(output_root: Path) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for market in MARKETS:
        path = output_root / market.lower() / "strategy_100pct_equity.parquet"
        if not path.exists():
            continue
        equity = pd.read_parquet(path)
        ts = pd.to_datetime(equity["ts"], utc=True, errors="raise")
        values = pd.Series(
            pd.to_numeric(equity["equity"], errors="coerce").to_numpy(dtype=float),
            index=ts,
        )
        daily = values.resample("1D").last().dropna()
        series[market] = daily.pct_change()
    if len(series) < 2:
        raise RuntimeError("Riskfolio candidate benchmark requires at least two markets")
    return pd.DataFrame(series).sort_index()


def run(output_root: Path) -> dict[str, Any]:
    returns = load_candidate_returns(output_root)
    root = output_root / "portfolio"
    rows: list[dict[str, Any]] = []

    for method in RISKFOLIO_METHODS:
        targets = build_riskfolio_targets(
            returns,
            method=method,
            lookback_days=180,
            min_observations=90,
            rebalance_frequency="M",
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
                "fallback_rebalance_count": fallback_rebalance_count,
                **metrics,
            }
        )

    comparison = pd.DataFrame(rows).sort_values(
        ["sharpe", "cagr"],
        ascending=[False, False],
        na_position="last",
    )
    comparison.to_csv(root / "riskfolio_portfolio_comparison.csv", index=False)
    payload = {
        "status": "READY",
        "rows": comparison.to_dict("records"),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(root / "riskfolio_portfolio_summary.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return payload


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Riskfolio benchmarks for Historical V2 candidate")
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    run(Path(args.output_dir).expanduser())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
