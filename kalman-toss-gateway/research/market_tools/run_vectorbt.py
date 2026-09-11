from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run reproducible vectorbt test on saved Kalman data")
    p.add_argument("--dataset", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def apply_rule(series: pd.Series, operator: str, value: float) -> pd.Series:
    if operator == ">":
        return series > value
    if operator == ">=":
        return series >= value
    if operator == "<":
        return series < value
    if operator == "<=":
        return series <= value
    raise ValueError(f"unsupported operator: {operator}")


def json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def main() -> int:
    args = parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if not cfg.get("research_only", False):
        raise RuntimeError("backtest config must explicitly set research_only=true")

    df = pd.read_parquet(args.dataset).sort_values("timestamp").reset_index(drop=True)
    price_col = cfg.get("price_column", "close")
    entry_cfg = cfg["entry"]
    exit_cfg = cfg["exit"]

    for col in [price_col, entry_cfg["feature"], exit_cfg["feature"]]:
        if col not in df.columns:
            raise ValueError(f"dataset missing column: {col}")

    index = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], errors="raise"))
    price = pd.Series(pd.to_numeric(df[price_col], errors="coerce").to_numpy(), index=index)
    entry_feature = pd.Series(
        pd.to_numeric(df[entry_cfg["feature"]], errors="coerce").to_numpy(),
        index=index,
    )
    exit_feature = pd.Series(
        pd.to_numeric(df[exit_cfg["feature"]], errors="coerce").to_numpy(),
        index=index,
    )

    valid = price.notna() & entry_feature.notna() & exit_feature.notna()
    price = price[valid]
    entries = apply_rule(entry_feature[valid], entry_cfg["operator"], float(entry_cfg["value"]))
    exits = apply_rule(exit_feature[valid], exit_cfg["operator"], float(exit_cfg["value"]))

    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=float(cfg.get("init_cash", 100000)),
        fees=float(cfg.get("fees", 0.0)),
        slippage=float(cfg.get("slippage", 0.0)),
        freq=cfg.get("freq", "1D"),
    )
    benchmark = vbt.Portfolio.from_holding(
        price,
        init_cash=float(cfg.get("init_cash", 100000)),
        fees=float(cfg.get("fees", 0.0)),
        slippage=float(cfg.get("slippage", 0.0)),
        freq=cfg.get("freq", "1D"),
    )

    stats = {str(k): json_value(v) for k, v in pf.stats().items()}
    benchmark_stats = {str(k): json_value(v) for k, v in benchmark.stats().items()}

    report = {
        "strategy_name": cfg["strategy_name"],
        "research_only": True,
        "dataset": str(Path(args.dataset)),
        "config": cfg,
        "rows": int(len(price)),
        "first_timestamp": None if price.empty else str(price.index[0]),
        "last_timestamp": None if price.empty else str(price.index[-1]),
        "entry_count": int(entries.sum()),
        "exit_count": int(exits.sum()),
        "strategy_stats": stats,
        "benchmark_stats": benchmark_stats,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(output)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
