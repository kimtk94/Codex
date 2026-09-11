from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simple RSI threshold walk-forward validation")
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--train", type=int, default=504)
    p.add_argument("--test", type=int, default=126)
    return p.parse_args()


def _sharpe(portfolio: Any) -> float:
    value = portfolio.sharpe_ratio()
    if hasattr(value, "item"):
        value = value.item()
    try:
        value = float(value)
    except Exception:
        return float("-inf")
    return value if np.isfinite(value) else float("-inf")


def _portfolio(price: pd.Series, rsi: pd.Series, entry: float, exit: float):
    return vbt.Portfolio.from_signals(
        price,
        rsi > entry,
        rsi < exit,
        init_cash=100000,
        fees=0.001,
        slippage=0.0005,
        freq="1D",
    )


def main() -> int:
    args = parse_args()
    df = pd.read_parquet(args.dataset).sort_values("timestamp").reset_index(drop=True)
    idx = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], errors="raise"))
    price = pd.Series(pd.to_numeric(df["close"], errors="coerce").to_numpy(), index=idx)
    rsi = pd.Series(pd.to_numeric(df["talib_v2_rsi14"], errors="coerce").to_numpy(), index=idx)
    valid = price.notna() & rsi.notna()
    price, rsi = price[valid], rsi[valid]

    entry_grid = [50.0, 55.0, 60.0]
    exit_grid = [40.0, 45.0, 50.0]
    windows: list[dict[str, Any]] = []

    start = 0
    while start + args.train + args.test <= len(price):
        train_slice = slice(start, start + args.train)
        test_slice = slice(start + args.train, start + args.train + args.test)
        train_price, train_rsi = price.iloc[train_slice], rsi.iloc[train_slice]
        test_price, test_rsi = price.iloc[test_slice], rsi.iloc[test_slice]

        best: tuple[float, float, float] | None = None
        for entry, exit in itertools.product(entry_grid, exit_grid):
            if exit >= entry:
                continue
            score = _sharpe(_portfolio(train_price, train_rsi, entry, exit))
            if best is None or score > best[2]:
                best = (entry, exit, score)

        if best is None:
            break
        entry, exit, train_sharpe = best
        test_pf = _portfolio(test_price, test_rsi, entry, exit)
        test_return = test_pf.total_return()
        if hasattr(test_return, "item"):
            test_return = test_return.item()

        windows.append({
            "train_start": str(train_price.index[0]),
            "train_end": str(train_price.index[-1]),
            "test_start": str(test_price.index[0]),
            "test_end": str(test_price.index[-1]),
            "entry_threshold": entry,
            "exit_threshold": exit,
            "train_sharpe": None if not np.isfinite(train_sharpe) else float(train_sharpe),
            "test_sharpe": None if not np.isfinite(_sharpe(test_pf)) else float(_sharpe(test_pf)),
            "test_total_return": float(test_return) if np.isfinite(test_return) else None,
        })
        start += args.test

    valid_returns = [w["test_total_return"] for w in windows if w["test_total_return"] is not None]
    report = {
        "research_only": True,
        "method": "rolling_walk_forward",
        "train_observations": args.train,
        "test_observations": args.test,
        "entry_grid": entry_grid,
        "exit_grid": exit_grid,
        "window_count": len(windows),
        "mean_test_return": float(np.mean(valid_returns)) if valid_returns else None,
        "positive_test_window_ratio": (
            float(np.mean([x > 0 for x in valid_returns])) if valid_returns else None
        ),
        "windows": windows,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
