from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from .lean_execution import ExecutionPolicy
from .lean_execution_runner import run_execution_contract
from .portfolio_targets import run_portfolio_target_layer
from .validate_artifacts import validate_output


MARKETS = ("US", "KR", "BTC")
REQUIRED_MARKET_ARTIFACTS = (
    "historical_model_output.parquet",
    "historical_strategy_signal.parquet",
    "fold_metrics.json",
    "experiment.json",
    "historical_trades.parquet",
    "historical_equity.parquet",
    "historical_performance.json",
    "run_summary.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def ready_markets_from_status(status: dict[str, Any]) -> list[str]:
    markets = []
    for market in MARKETS:
        item = status.get("markets", {}).get(market, {})
        if item.get("status") == "READY":
            markets.append(market)
    return markets


def validate_reusable_market_artifacts(
    output_root: Path,
    markets: list[str],
) -> None:
    if len(markets) < 2:
        raise RuntimeError("resume requires at least two READY market sleeves")

    missing: list[str] = []
    for market in markets:
        market_dir = output_root / market.lower()
        for name in REQUIRED_MARKET_ARTIFACTS:
            if not (market_dir / name).exists():
                missing.append(f"{market}/{name}")
    if missing:
        raise FileNotFoundError(
            "missing reusable historical artifacts: " + ", ".join(missing)
        )


def _portfolio_status(portfolio, markets: list[str], method: str) -> dict[str, Any]:
    return {
        "status": "READY",
        "method": method,
        "markets": markets,
        "target_rows": int(len(portfolio.targets)),
        "rebalance_count": int(portfolio.targets["effective_ts"].nunique()),
        "performance": portfolio.metrics,
        "source": "PYPFOPT" if method in {"hrp", "max_sharpe"} else "KALMAN",
        "live_execution": False,
        "neon_write": False,
    }


def resume_postprocess(
    output_root: Path,
    *,
    method: str = "hrp",
    lookback_days: int = 180,
    min_observations: int = 90,
    rebalance_frequency: str = "M",
    initial_cash: float = 1_000_000.0,
) -> dict[str, Any]:
    output_root = output_root.expanduser()
    status_path = output_root / "historical_experiment_status.json"
    status = _load_json(status_path)
    markets = ready_markets_from_status(status)
    validate_reusable_market_artifacts(output_root, markets)

    # Rebuild only post-processing artifacts. Historical market folders are
    # intentionally immutable inputs for resume.
    shutil.rmtree(output_root / "portfolio", ignore_errors=True)
    shutil.rmtree(output_root / "execution", ignore_errors=True)

    resume_status_path = output_root / "resume_postprocess_status.json"
    _write_json(
        resume_status_path,
        {
            "status": "RUNNING",
            "historical_reused": True,
            "markets": markets,
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
        },
    )

    try:
        portfolio = run_portfolio_target_layer(
            output_root,
            markets=markets,
            method=method,
            lookback_days=lookback_days,
            min_observations=min_observations,
            rebalance_frequency=rebalance_frequency,
        )

        status["status"] = "READY"
        status["portfolio"] = _portfolio_status(portfolio, markets, method)
        status["postprocess_resume"] = {
            "historical_reused": True,
            "market_backtests_rerun": False,
        }
        _write_json(status_path, status)

        validation = validate_output(output_root)
        _write_json(output_root / "historical_validation_report.json", validation)
        if validation.get("status") != "READY":
            raise RuntimeError(
                "historical artifact validation failed: "
                + json.dumps(validation.get("errors", []), ensure_ascii=False)
            )

        execution = run_execution_contract(
            output_root,
            initial_cash=initial_cash,
            policy=ExecutionPolicy(
                max_symbol_weight=0.75,
                max_gross_weight=1.0,
                min_order_notional=10.0,
                max_single_order_fraction=0.80,
                max_total_turnover_fraction=2.0,
                broker="SHADOW",
                slippage_bps=0.0,
                commission_bps=0.0,
                allow_live_execution=False,
            ),
        )

        resume_status = {
            "status": "READY_CORE",
            "historical_reused": True,
            "market_backtests_rerun": False,
            "markets": markets,
            "portfolio": status["portfolio"],
            "validation": validation,
            "execution": execution,
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
        }
        _write_json(resume_status_path, resume_status)
        return resume_status
    except Exception as exc:
        status["status"] = "FAIL"
        status["postprocess_resume"] = {
            "historical_reused": True,
            "market_backtests_rerun": False,
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _write_json(status_path, status)
        _write_json(
            resume_status_path,
            {
                "status": "FAIL",
                "historical_reused": True,
                "market_backtests_rerun": False,
                "markets": markets,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "research_only": True,
                "live_execution": False,
                "toss_execution": False,
                "neon_write": False,
            },
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resume Kalman historical run from portfolio post-processing"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--method", default="hrp")
    parser.add_argument("--lookback-days", type=int, default=180)
    parser.add_argument("--min-observations", type=int, default=90)
    parser.add_argument("--rebalance", choices=["M", "Q"], default="M")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = resume_postprocess(
        Path(args.output_dir),
        method=args.method,
        lookback_days=args.lookback_days,
        min_observations=args.min_observations,
        rebalance_frequency=args.rebalance,
        initial_cash=args.initial_cash,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
