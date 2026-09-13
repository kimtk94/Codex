from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

MARKETS = ("US", "KR", "BTC")


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


def _raw_path_from_manifest(manifest: dict[str, Any]) -> Path:
    anchor_key = str(manifest["anchor_key"])
    for path, metadata in manifest.get("input_files", {}).items():
        if (
            str(metadata.get("kind")) == "raw"
            and str(metadata.get("fetch_key")) == anchor_key
        ):
            candidate = Path(path).expanduser()
            if candidate.exists():
                return candidate
    raise FileNotFoundError(f"raw anchor path not found for {anchor_key}")


def _map_signals_to_next_bar(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
) -> dict[int, list[str]]:
    ts = pd.DatetimeIndex(bars["timestamp"])
    mapped: dict[int, list[str]] = {}
    for row in signals.sort_values("signal_ts").itertuples(index=False):
        signal_ts = pd.Timestamp(row.signal_ts)
        i = int(ts.searchsorted(signal_ts, side="right"))
        if i >= len(ts):
            continue
        mapped.setdefault(i, []).append(str(row.signal).upper().strip())
    return mapped


def _stateful_entry_exit_arrays(
    event_map: dict[int, list[str]],
    n: int,
    *,
    max_hold_bars: int,
) -> tuple[np.ndarray, np.ndarray]:
    entries = np.zeros(n, dtype=bool)
    exits = np.zeros(n, dtype=bool)
    in_position = False
    bars_held = 0

    for i in range(n):
        actions = event_map.get(i, [])

        if in_position and any(action == "SELL" for action in actions):
            exits[i] = True
            in_position = False
            bars_held = 0

        if (not in_position) and any(action == "BUY" for action in actions):
            entries[i] = True
            in_position = True
            bars_held = 0

        if in_position:
            bars_held += 1
            if bars_held >= max_hold_bars:
                exits[i] = True
                in_position = False
                bars_held = 0

    return entries, exits


def _scalar(value: Any) -> float | int | None:
    if hasattr(value, "item"):
        value = value.item()
    try:
        number = float(value)
    except Exception:
        return None
    if not np.isfinite(number):
        return None
    if float(number).is_integer():
        return int(number)
    return float(number)


def _metrics(pf: Any) -> dict[str, Any]:
    return {
        "total_return": _scalar(pf.total_return()),
        "sharpe": _scalar(pf.sharpe_ratio()),
        "max_drawdown": _scalar(pf.max_drawdown()),
        "trade_count": _scalar(pf.trades.count()),
        "ending_value": _scalar(pf.value().iloc[-1] if len(pf.value()) else np.nan),
    }


def validate_market(
    output_root: Path,
    matrix_dir: Path,
    market: str,
    *,
    init_cash: float = 1_000_000.0,
    max_hold_bars: int = 20,
) -> dict[str, Any]:
    market_dir = output_root / market.lower()
    signals = pd.read_parquet(market_dir / "historical_strategy_signal.parquet")
    signals["signal_ts"] = pd.to_datetime(signals["signal_ts"], utc=True, errors="raise")

    manifest = _load_json(matrix_dir / f"{market.lower()}_matrix_manifest.json")
    raw_path = _raw_path_from_manifest(manifest)
    raw = pd.read_parquet(raw_path)

    required = {"timestamp", "open", "close"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"{raw_path} missing columns: {sorted(missing)}")

    bars = raw.loc[:, ["timestamp", "open", "close"]].copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True, errors="raise")
    bars["open"] = pd.to_numeric(bars["open"], errors="coerce")
    bars["close"] = pd.to_numeric(bars["close"], errors="coerce")
    bars = (
        bars.dropna()
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )

    event_map = _map_signals_to_next_bar(signals, bars)
    entries, exits = _stateful_entry_exit_arrays(
        event_map,
        len(bars),
        max_hold_bars=max_hold_bars,
    )

    index = pd.DatetimeIndex(bars["timestamp"])
    execution_price = pd.Series(bars["open"].to_numpy(dtype=float), index=index)

    pf = vbt.Portfolio.from_signals(
        execution_price,
        pd.Series(entries, index=index),
        pd.Series(exits, index=index),
        init_cash=init_cash,
        size=0.10,
        size_type="percent",
        fees=0.0005,
        slippage=0.0005,
        freq="1D",
    )
    benchmark = vbt.Portfolio.from_holding(
        execution_price,
        init_cash=init_cash,
        fees=0.0005,
        slippage=0.0005,
        freq="1D",
    )

    native = _load_json(market_dir / "historical_performance.json")
    vector_metrics = _metrics(pf)
    benchmark_metrics = _metrics(benchmark)

    native_return = native.get("total_return")
    vector_return = vector_metrics.get("total_return")
    return_gap = None
    if native_return is not None and vector_return is not None:
        return_gap = float(vector_return) - float(native_return)

    return {
        "status": "READY",
        "market": market,
        "validator": "VECTORBT_1_1_0",
        "validation_scope": "NEXT_BAR_DIRECTIONAL_REPLAY",
        "execution_price": "NEXT_BAR_OPEN",
        "position_sizing": "10_PERCENT_AVAILABLE_CASH_APPROXIMATION",
        "max_hold_bars": max_hold_bars,
        "fees": 0.0005,
        "slippage": 0.0005,
        "note": (
            "Independent validator, not execution-truth parity. Kalman native ledger "
            "remains authoritative; vectorbt target/percent semantics can differ slightly."
        ),
        "rows": int(len(bars)),
        "mapped_event_bars": int(len(event_map)),
        "entry_count": int(entries.sum()),
        "exit_count": int(exits.sum()),
        "native_metrics": native,
        "vectorbt_metrics": vector_metrics,
        "buy_and_hold_metrics": benchmark_metrics,
        "vectorbt_minus_native_total_return": return_gap,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Independent vectorbt validation for Kalman historical run")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--max-hold-bars", type=int, default=20)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_dir).expanduser()
    matrix_dir = Path(args.matrix_dir).expanduser()
    out_dir = output_root / "analysis_v2" / "vectorbt"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}
    for market in MARKETS:
        try:
            result = validate_market(
                output_root,
                matrix_dir,
                market,
                max_hold_bars=args.max_hold_bars,
            )
        except Exception as exc:
            result = {
                "status": "FAIL",
                "market": market,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        results[market] = result
        _write_json(out_dir / f"{market.lower()}_vectorbt_validation.json", result)

    ready = [m for m, result in results.items() if result.get("status") == "READY"]
    payload = {
        "status": "READY" if len(ready) == len(MARKETS) else "DEGRADED",
        "ready_markets": ready,
        "markets": results,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _write_json(out_dir / "vectorbt_validation_summary.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
