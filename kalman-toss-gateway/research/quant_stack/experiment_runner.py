from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import BacktestConfig, ExperimentSpec, Mode
from .historical_backfill import run_historical_backfill, write_backfill_artifacts
from .native_ledger import run_backtest


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run Kalman historical walk-forward backfill + native ledger"
    )
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--market", action="append", choices=["US", "KR", "BTC"])
    p.add_argument("--start-date", default="2017-01-01")
    p.add_argument("--train", type=int, default=504)
    p.add_argument("--valid", type=int, default=63)
    p.add_argument("--test", type=int, default=126)
    p.add_argument("--max-hold-bars", type=int, default=20)
    p.add_argument("--git-sha")
    return p.parse_args()


def _load_anchor_prices(
    manifest: dict[str, Any],
    matrix: pd.DataFrame,
) -> pd.DataFrame:
    anchor_key = str(manifest["anchor_key"])
    input_files = manifest.get("input_files", {})

    raw_path: Path | None = None
    for path, metadata in input_files.items():
        if (
            str(metadata.get("kind")) == "raw"
            and str(metadata.get("fetch_key")) == anchor_key
        ):
            raw_path = Path(path).expanduser()
            break

    if raw_path is not None and raw_path.exists():
        raw = pd.read_parquet(raw_path)
        required = {"timestamp", "open", "close"}
        missing = required.difference(raw.columns)
        if missing:
            raise ValueError(f"anchor raw file missing columns: {sorted(missing)}")
        out = pd.DataFrame(
            {
                "symbol": str(manifest["symbol"]),
                "ts": pd.to_datetime(raw["timestamp"], utc=True, errors="raise"),
                "open": pd.to_numeric(raw["open"], errors="coerce"),
                "close": pd.to_numeric(raw["close"], errors="coerce"),
            }
        )
        return out.dropna().sort_values("ts").drop_duplicates("ts", keep="last")

    # Fallback is explicit and conservative: use next observed anchor close as both
    # open and close only when the original raw artifact is unavailable.
    out = pd.DataFrame(
        {
            "symbol": str(manifest["symbol"]),
            "ts": pd.to_datetime(matrix["as_of"], utc=True, errors="raise"),
            "open": pd.to_numeric(matrix["anchor_close"], errors="coerce"),
            "close": pd.to_numeric(matrix["anchor_close"], errors="coerce"),
        }
    )
    out = out.dropna().sort_values("ts").drop_duplicates("ts", keep="last")
    out.attrs["price_fallback"] = "ANCHOR_CLOSE_AS_OPEN"
    return out


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def run_market(
    *,
    market_name: str,
    matrix_dir: Path,
    global_spec: dict[str, Any],
    output_root: Path,
    start_date: str,
    train_observations: int,
    valid_observations: int,
    test_observations: int,
    max_hold_bars: int,
    git_sha: str | None,
) -> dict[str, Any]:
    market_spec = global_spec["markets"][market_name]
    matrix_path = matrix_dir / f"{market_name.lower()}_matrix.parquet"
    manifest_path = matrix_dir / f"{market_name.lower()}_matrix_manifest.json"

    if not matrix_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(f"missing matrix artifacts for {market_name}")

    matrix = pd.read_parquet(matrix_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    experiment_spec = ExperimentSpec(
        experiment_name=f"kalman_2017_walk_forward_{market_name.lower()}",
        market=market_name,
        feature_version=str(global_spec["feature_set"]),
        model_version=str(global_spec["version"]),
        start_date=start_date,
        mode=Mode.BACKTEST,
        git_sha=git_sha,
        notes="Historical prospective-only fold reconstruction",
    )

    result = run_historical_backfill(
        matrix,
        market_name=market_name,
        market_spec=market_spec,
        global_spec=global_spec,
        experiment_spec=experiment_spec,
        train_observations=train_observations,
        valid_observations=valid_observations,
        test_observations=test_observations,
        purge_observations=int(market_spec["horizon_observations"]),
        expanding=True,
    )

    market_output = output_root / market_name.lower()
    write_backfill_artifacts(result, market_output)

    prices = _load_anchor_prices(manifest, matrix)
    signals = result.strategy_signal[
        ["symbol", "signal_ts", "signal", "entry_allowed"]
    ].copy()
    backtest = run_backtest(
        signals,
        prices,
        BacktestConfig(
            initial_cash=1_000_000.0,
            position_fraction=0.10,
            max_open_positions=1,
            commission_bps=5.0,
            slippage_bps=5.0,
            max_hold_bars=max_hold_bars,
            allow_fractional=True,
        ),
    )

    backtest.trades.to_parquet(market_output / "historical_trades.parquet", index=False)
    backtest.equity.to_parquet(market_output / "historical_equity.parquet", index=False)
    _json_write(market_output / "historical_performance.json", backtest.metrics)

    summary = {
        "market": market_name,
        "experiment_hash": result.experiment["experiment_hash"],
        "completed_folds": result.experiment["completed_folds"],
        "model_output_rows": len(result.model_output),
        "signal_counts": result.experiment["signal_counts"],
        "trade_count": int(backtest.metrics.get("trade_count", 0)),
        "performance": backtest.metrics,
        "price_source": (
            "ANCHOR_CLOSE_AS_OPEN"
            if prices.attrs.get("price_fallback")
            else "RAW_ANCHOR_OHLC"
        ),
    }
    _json_write(market_output / "run_summary.json", summary)
    return summary


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    output_root = Path(args.output_dir).expanduser()
    global_spec = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))
    markets = args.market or ["US", "KR", "BTC"]

    status: dict[str, Any] = {
        "status": "READY",
        "research_only": True,
        "live_execution": False,
        "neon_write": False,
        "markets": {},
    }

    for market_name in markets:
        try:
            status["markets"][market_name] = {
                "status": "READY",
                **run_market(
                    market_name=market_name,
                    matrix_dir=matrix_dir,
                    global_spec=global_spec,
                    output_root=output_root,
                    start_date=args.start_date,
                    train_observations=args.train,
                    valid_observations=args.valid,
                    test_observations=args.test,
                    max_hold_bars=args.max_hold_bars,
                    git_sha=args.git_sha,
                ),
            }
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market_name] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    _json_write(output_root / "historical_experiment_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
