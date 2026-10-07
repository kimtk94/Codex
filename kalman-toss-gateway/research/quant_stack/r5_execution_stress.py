from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCHEMA_VERSION = "kalman-r5-execution-stress-v1"
DEFAULT_SLIPPAGE_BPS = (0.0, 10.0, 25.0, 50.0, 100.0)


def _price_frame(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    required = {"expected_seq", "open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    cols = ["expected_seq", "open", "high", "low", "close"]
    if "quote_volume" in df.columns:
        cols.append("quote_volume")
    elif "volume" in df.columns:
        cols.append("volume")
    out = df[cols].copy()
    for col in cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["expected_seq", "open", "high", "low", "close"])
    out["expected_seq"] = out["expected_seq"].astype("int64")
    if "quote_volume" not in out.columns:
        if "volume" in out.columns:
            out["quote_volume"] = out["volume"] * out["close"]
        else:
            out["quote_volume"] = np.nan
    return out.sort_values("expected_seq").drop_duplicates("expected_seq", keep="last")


class PriceCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._cache: dict[str, pd.DataFrame] = {}

    def frame(self, symbol: str) -> pd.DataFrame:
        symbol = str(symbol).upper().replace(".", "-")
        if symbol not in self._cache:
            path = self.root / f"{symbol}_1h_gap_aware.parquet"
            if not path.is_file():
                self._cache[symbol] = pd.DataFrame()
            else:
                self._cache[symbol] = _price_frame(path)
        return self._cache[symbol]


def simulate_trade(
    frame: pd.DataFrame,
    *,
    entry_seq: int,
    exit_seq: int,
    stop_pct: float,
    slippage_bps: float,
    cost_bps: float,
) -> dict[str, Any] | None:
    path = frame.loc[frame["expected_seq"].between(int(entry_seq), int(exit_seq))].copy()
    if path.empty:
        return None
    entry_row = path.loc[path["expected_seq"].eq(int(entry_seq))]
    exit_row = path.loc[path["expected_seq"].eq(int(exit_seq))]
    if entry_row.empty or exit_row.empty:
        return None

    entry_open = float(entry_row.iloc[-1]["open"])
    if not np.isfinite(entry_open) or entry_open <= 0:
        return None

    slip = float(slippage_bps) / 10000.0
    entry_fill = entry_open * (1.0 + slip)
    stop_price = entry_fill * (1.0 + float(stop_pct))

    exit_fill = None
    exit_reason = "FIXED_EXIT"
    stop_seq = None
    gap_through = False
    stop_overshoot_pct = 0.0

    for _, bar in path.sort_values("expected_seq").iterrows():
        seq = int(bar["expected_seq"])
        bar_open = float(bar["open"])
        bar_low = float(bar["low"])
        if seq == int(entry_seq):
            if bar_low <= stop_price:
                exit_fill = stop_price * (1.0 - slip)
                exit_reason = "STOP_INTRABAR"
                stop_seq = seq
                break
            continue
        if bar_open <= stop_price:
            exit_fill = bar_open * (1.0 - slip)
            exit_reason = "STOP_GAP_THROUGH"
            stop_seq = seq
            gap_through = True
            stop_overshoot_pct = bar_open / stop_price - 1.0
            break
        if bar_low <= stop_price:
            exit_fill = stop_price * (1.0 - slip)
            exit_reason = "STOP_INTRABAR"
            stop_seq = seq
            break

    if exit_fill is None:
        exit_close = float(exit_row.iloc[-1]["close"])
        exit_fill = exit_close * (1.0 - slip)

    gross_return = exit_fill / entry_fill - 1.0
    net_return = gross_return - float(cost_bps) / 10000.0
    entry_quote_volume = float(entry_row.iloc[-1].get("quote_volume", np.nan))
    return {
        "entry_fill": entry_fill,
        "stop_price": stop_price,
        "exit_fill": exit_fill,
        "gross_return": gross_return,
        "net_return": net_return,
        "exit_reason": exit_reason,
        "stop_seq": stop_seq,
        "gap_through": gap_through,
        "stop_overshoot_pct": stop_overshoot_pct,
        "entry_quote_volume": entry_quote_volume,
    }


def metrics(returns: pd.Series) -> dict[str, Any]:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    if r.empty:
        return {}
    wealth = (1.0 + r).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    return {
        "trades": int(len(r)),
        "total_return": float(wealth.iloc[-1] - 1.0),
        "max_drawdown": float(dd.min()),
        "mean_return": float(r.mean()),
        "median_return": float(r.median()),
        "win_rate": float((r > 0).mean()),
        "worst_trade": float(r.min()),
    }


def run(panel: pd.DataFrame, price_root: Path, *, stop_pct: float, slippages: tuple[float, ...], cost_bps: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    cache = PriceCache(price_root)
    details = []
    summaries = []
    for bps in slippages:
        rows = []
        for row in panel.itertuples(index=False):
            symbol = str(row.rank1_symbol)
            sim = simulate_trade(
                cache.frame(symbol),
                entry_seq=int(row.entry_expected_seq),
                exit_seq=int(row.actual_exit_seq),
                stop_pct=stop_pct,
                slippage_bps=bps,
                cost_bps=cost_bps,
            )
            if sim is None:
                continue
            record = {
                "expected_seq": int(row.expected_seq),
                "symbol": symbol,
                "entry_expected_seq": int(row.entry_expected_seq),
                "actual_exit_seq": int(row.actual_exit_seq),
                "slippage_bps_each_side": float(bps),
                **sim,
            }
            rows.append(record)
            details.append(record)
        frame = pd.DataFrame(rows)
        m = metrics(frame["net_return"] if not frame.empty else pd.Series(dtype=float))
        if frame.empty:
            summaries.append({"slippage_bps_each_side": bps, **m})
            continue
        stop_mask = frame["exit_reason"].str.startswith("STOP")
        qv = pd.to_numeric(frame["entry_quote_volume"], errors="coerce").dropna()
        summaries.append({
            "slippage_bps_each_side": float(bps),
            "stop_pct": float(stop_pct),
            **m,
            "stop_trigger_count": int(stop_mask.sum()),
            "stop_trigger_rate": float(stop_mask.mean()),
            "gap_through_count": int(frame["gap_through"].sum()),
            "gap_through_rate": float(frame["gap_through"].mean()),
            "worst_gap_overshoot_pct": float(frame["stop_overshoot_pct"].min()),
            "entry_quote_volume_p01": float(qv.quantile(0.01)) if len(qv) else None,
            "entry_quote_volume_p05": float(qv.quantile(0.05)) if len(qv) else None,
            "entry_quote_volume_median": float(qv.median()) if len(qv) else None,
        })
    return pd.DataFrame(details), pd.DataFrame(summaries)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--price-root", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--stop-pct", type=float, default=-0.03)
    p.add_argument("--cost-bps", type=float, default=10.0)
    p.add_argument("--slippage-bps", default=",".join(str(x) for x in DEFAULT_SLIPPAGE_BPS))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    panel = pd.read_parquet(args.panel)
    slippages = tuple(float(x.strip()) for x in args.slippage_bps.split(",") if x.strip())
    detail, summary = run(panel, args.price_root, stop_pct=args.stop_pct, slippages=slippages, cost_bps=args.cost_bps)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_parquet(args.output_dir / "execution_stress_detail.parquet", index=False)
    summary.to_csv(args.output_dir / "execution_stress_summary.csv", index=False)
    status = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "panel": str(args.panel),
        "price_root": str(args.price_root),
        "stop_pct": args.stop_pct,
        "cost_bps": args.cost_bps,
        "slippage_bps_each_side": list(slippages),
        "summary": summary.to_dict(orient="records"),
    }
    (args.output_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
