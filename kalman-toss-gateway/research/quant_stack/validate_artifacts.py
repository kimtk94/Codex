from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


ALLOWED_SIGNALS = {"BUY", "SELL", "HOLD"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate Kalman historical quant artifacts")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--report")
    return p.parse_args()


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_market(root: Path, market: str) -> dict[str, Any]:
    market_dir = root / market.lower()
    errors: list[str] = []
    warnings: list[str] = []

    required = {
        "historical_model_output.parquet",
        "historical_strategy_signal.parquet",
        "fold_metrics.json",
        "experiment.json",
        "historical_trades.parquet",
        "historical_equity.parquet",
        "historical_performance.json",
        "run_summary.json",
    }
    missing = sorted(name for name in required if not (market_dir / name).exists())
    if missing:
        return {
            "status": "FAIL",
            "errors": [f"missing artifacts: {missing}"],
            "warnings": [],
        }

    model_output = pd.read_parquet(market_dir / "historical_model_output.parquet")
    signals = pd.read_parquet(market_dir / "historical_strategy_signal.parquet")
    folds = _load_json(market_dir / "fold_metrics.json")
    experiment = _load_json(market_dir / "experiment.json")
    performance = _load_json(market_dir / "historical_performance.json")
    summary = _load_json(market_dir / "run_summary.json")

    if str(experiment.get("mode")) != "BACKTEST":
        errors.append(f"experiment mode is not BACKTEST: {experiment.get('mode')!r}")

    if summary.get("price_source") != "RAW_ANCHOR_OHLC":
        errors.append(
            "price_source must be RAW_ANCHOR_OHLC; "
            f"got {summary.get('price_source')!r}"
        )

    if model_output.empty:
        errors.append("historical_model_output is empty")
    else:
        required_model_cols = {
            "run_id",
            "market",
            "symbol",
            "as_of",
            "fold_id",
            "probability",
            "probability_threshold",
        }
        missing_model = required_model_cols.difference(model_output.columns)
        if missing_model:
            errors.append(f"model_output missing columns: {sorted(missing_model)}")
        else:
            if model_output.duplicated(["market", "symbol", "as_of"]).any():
                errors.append("duplicate model_output market/symbol/as_of rows")
            probability = pd.to_numeric(model_output["probability"], errors="coerce")
            if probability.isna().any() or ((probability < 0) | (probability > 1)).any():
                errors.append("model_output probability outside [0, 1] or non-numeric")

    if signals.empty:
        errors.append("historical_strategy_signal is empty")
    else:
        required_signal_cols = {
            "symbol",
            "signal_ts",
            "signal",
            "entry_allowed",
            "probability",
            "probability_threshold",
            "exit_threshold",
            "fold_id",
            "run_id",
        }
        missing_signal = required_signal_cols.difference(signals.columns)
        if missing_signal:
            errors.append(f"strategy_signal missing columns: {sorted(missing_signal)}")
        else:
            unique_signals = set(signals["signal"].astype(str).str.upper())
            invalid = sorted(unique_signals.difference(ALLOWED_SIGNALS))
            if invalid:
                errors.append(f"invalid signals: {invalid}")

            entry_allowed = signals["entry_allowed"].fillna(False).astype(bool)
            buy = signals["signal"].astype(str).str.upper().eq("BUY")
            if not (entry_allowed == buy).all():
                errors.append("entry_allowed must be true only for BUY decisions")

            if len(signals) != len(model_output):
                errors.append(
                    f"signal/model_output row mismatch: {len(signals)} != {len(model_output)}"
                )

    previous_test_end: pd.Timestamp | None = None
    for i, item in enumerate(folds):
        fold = item.get("fold", {})
        try:
            train_end = pd.Timestamp(fold["train_end"])
            valid_start = pd.Timestamp(fold["valid_start"])
            valid_end = pd.Timestamp(fold["valid_end"])
            test_start = pd.Timestamp(fold["test_start"])
            test_end = pd.Timestamp(fold["test_end"])
        except Exception as exc:
            errors.append(f"fold {i} date parse failure: {exc}")
            continue

        if not train_end < valid_start:
            errors.append(f"fold {i} train/validation leakage")
        if not valid_end < test_start:
            errors.append(f"fold {i} validation/test leakage")
        if test_end < test_start:
            errors.append(f"fold {i} invalid test range")
        if previous_test_end is not None and test_start <= previous_test_end:
            errors.append(f"fold {i} overlaps previous test window")
        previous_test_end = test_end

        selected = item.get("selected_features", [])
        if len(selected) < 5:
            errors.append(f"fold {i} selected fewer than 5 features")

    signal_counts = {
        str(k): int(v)
        for k, v in signals["signal"].astype(str).str.upper().value_counts().to_dict().items()
    } if not signals.empty and "signal" in signals else {}

    if signal_counts.get("BUY", 0) == 0:
        warnings.append("no BUY decisions generated")
    if signal_counts.get("SELL", 0) == 0:
        warnings.append("no SELL decisions generated")

    trade_count = int(performance.get("trade_count", 0) or 0)
    if trade_count == 0:
        warnings.append("native ledger produced zero closed trades")

    return {
        "status": "READY" if not errors else "FAIL",
        "ready_for_neon": not errors,
        "errors": errors,
        "warnings": warnings,
        "completed_folds": len(folds),
        "model_output_rows": int(len(model_output)),
        "signal_rows": int(len(signals)),
        "signal_counts": signal_counts,
        "trade_count": trade_count,
        "price_source": summary.get("price_source"),
    }


def validate_output(root: Path) -> dict[str, Any]:
    status = _load_json(root / "historical_experiment_status.json")
    errors: list[str] = []

    if status.get("status") != "READY":
        errors.append(f"experiment status is not READY: {status.get('status')!r}")
    if status.get("research_only") is not True:
        errors.append("research_only invariant failed")
    if status.get("live_execution") is not False:
        errors.append("live_execution invariant failed")
    if status.get("neon_write") is not False:
        errors.append("neon_write invariant failed")

    markets = sorted(status.get("markets", {}).keys())
    market_reports = {market: _validate_market(root, market) for market in markets}
    if not markets:
        errors.append("no markets in historical experiment status")

    for market, report in market_reports.items():
        if report["status"] != "READY":
            errors.append(f"{market} validation failed")

    return {
        "status": "READY" if not errors else "FAIL",
        "ready_for_neon": not errors,
        "research_only": True,
        "live_execution": False,
        "neon_write": False,
        "errors": errors,
        "markets": market_reports,
    }


def main() -> int:
    args = parse_args()
    root = Path(args.output_dir).expanduser()
    report = validate_output(root)
    report_path = (
        Path(args.report).expanduser()
        if args.report
        else root / "historical_validation_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
