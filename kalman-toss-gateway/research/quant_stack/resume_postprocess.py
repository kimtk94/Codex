from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ready_markets_from_status(status: dict[str, Any]) -> list[str]:
    markets = []
    for market in MARKETS:
        item = status.get("markets", {}).get(market, {})
        if item.get("status") == "READY":
            markets.append(market)
    return markets


def validate_status_safety_invariants(status: dict[str, Any]) -> None:
    if status.get("research_only") is not True:
        raise RuntimeError("resume requires research_only=true")
    if status.get("live_execution") is not False:
        raise RuntimeError("resume requires live_execution=false")
    if status.get("neon_write") is not False:
        raise RuntimeError("resume requires neon_write=false")
    if status.get("toss_execution") not in (None, False):
        raise RuntimeError("resume requires toss_execution=false")


def _validate_json_artifact(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if path.name == "experiment.json":
        if not isinstance(payload, dict) or payload.get("mode") != "BACKTEST":
            raise ValueError(f"{path} must have mode=BACKTEST")
    elif path.name == "run_summary.json":
        if not isinstance(payload, dict):
            raise ValueError(f"{path} must contain a JSON object")
        if payload.get("price_source") != "RAW_ANCHOR_OHLC":
            raise ValueError(f"{path} must use RAW_ANCHOR_OHLC")
    elif path.name == "fold_metrics.json":
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"{path} must contain non-empty fold metrics")
    elif not isinstance(payload, (dict, list)):
        raise ValueError(f"{path} contains unsupported JSON payload")


def _validate_parquet_artifact(path: Path) -> None:
    frame = pd.read_parquet(path)
    if path.name in {
        "historical_model_output.parquet",
        "historical_strategy_signal.parquet",
        "historical_equity.parquet",
    } and frame.empty:
        raise ValueError(f"{path} must not be empty")

    if path.name == "historical_equity.parquet":
        missing = {"ts", "equity"}.difference(frame.columns)
        if missing:
            raise ValueError(
                f"{path} missing columns: {sorted(missing)}"
            )
        equity = pd.to_numeric(frame["equity"], errors="coerce")
        if equity.isna().any() or not (equity > 0).all():
            raise ValueError(f"{path} contains invalid equity values")


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
            path = market_dir / name
            if not path.exists():
                missing.append(f"{market}/{name}")
                continue
            if path.stat().st_size <= 0:
                raise ValueError(f"empty reusable artifact: {path}")
            if path.suffix == ".json":
                _validate_json_artifact(path)
            elif path.suffix == ".parquet":
                _validate_parquet_artifact(path)

    if missing:
        raise FileNotFoundError(
            "missing reusable historical artifacts: " + ", ".join(missing)
        )


def market_artifact_fingerprint(
    output_root: Path,
    markets: list[str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for market in markets:
        for name in REQUIRED_MARKET_ARTIFACTS:
            path = output_root / market.lower() / name
            result[f"{market}/{name}"] = _sha256_file(path)
    return result


def assert_market_artifacts_unchanged(
    output_root: Path,
    markets: list[str],
    expected: dict[str, str],
) -> None:
    actual = market_artifact_fingerprint(output_root, markets)
    changed = sorted(
        key for key, digest in expected.items() if actual.get(key) != digest
    )
    if changed:
        raise RuntimeError(
            "resume modified immutable historical market artifacts: "
            + ", ".join(changed)
        )


def preflight_resume(output_root: Path) -> dict[str, Any]:
    output_root = output_root.expanduser()
    status_path = output_root / "historical_experiment_status.json"
    status = _load_json(status_path)
    validate_status_safety_invariants(status)

    markets = ready_markets_from_status(status)
    validate_reusable_market_artifacts(output_root, markets)
    fingerprint = market_artifact_fingerprint(output_root, markets)

    report = {
        "status": "READY",
        "historical_reused": True,
        "market_backtests_rerun": False,
        "markets": markets,
        "immutable_artifact_count": len(fingerprint),
        "immutable_fingerprint": fingerprint,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(output_root / "resume_preflight_report.json", report)
    return report


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
    original_status = _load_json(status_path)
    preflight = preflight_resume(output_root)
    markets = list(preflight["markets"])
    baseline_fingerprint = dict(preflight["immutable_fingerprint"])

    resume_status_path = output_root / "resume_postprocess_status.json"
    _write_json(
        resume_status_path,
        {
            "status": "RUNNING",
            "phase": "PORTFOLIO",
            "historical_reused": True,
            "market_backtests_rerun": False,
            "markets": markets,
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
        },
    )

    # Only post-processing directories are disposable. Historical market
    # artifacts are fingerprinted above and verified again before success.
    shutil.rmtree(output_root / "portfolio", ignore_errors=True)
    shutil.rmtree(output_root / "execution", ignore_errors=True)

    try:
        portfolio = run_portfolio_target_layer(
            output_root,
            markets=markets,
            method=method,
            lookback_days=lookback_days,
            min_observations=min_observations,
            rebalance_frequency=rebalance_frequency,
        )

        status = copy.deepcopy(original_status)
        status["status"] = "READY"
        status["portfolio"] = _portfolio_status(portfolio, markets, method)
        status["postprocess_resume"] = {
            "historical_reused": True,
            "market_backtests_rerun": False,
            "status": "READY",
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

        assert_market_artifacts_unchanged(
            output_root,
            markets,
            baseline_fingerprint,
        )

        resume_status = {
            "status": "READY_CORE",
            "historical_reused": True,
            "market_backtests_rerun": False,
            "markets": markets,
            "portfolio": status["portfolio"],
            "validation": validation,
            "execution": execution,
            "immutable_market_artifacts_verified": True,
            "research_only": True,
            "live_execution": False,
            "toss_execution": False,
            "neon_write": False,
        }
        _write_json(resume_status_path, resume_status)
        return resume_status
    except Exception as exc:
        # Never leave the source historical run's status mutated by a failed
        # resume attempt.
        _write_json(status_path, original_status)
        _write_json(
            resume_status_path,
            {
                "status": "FAIL",
                "historical_reused": True,
                "market_backtests_rerun": False,
                "markets": markets,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "original_status_restored": True,
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
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_dir)
    if args.preflight_only:
        result = preflight_resume(output_root)
    else:
        result = resume_postprocess(
            output_root,
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
