from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.quant_stack.contracts import BacktestConfig
from research.quant_stack.historical_v2_candidate import _load_prices
from research.quant_stack.native_ledger import run_backtest

MARKETS = ("US", "KR", "BTC")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Replay V3 vs Macro-V4 on identical OOS windows"
    )
    p.add_argument("--v3-root", required=True)
    p.add_argument("--v4-root", required=True)
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def compare_market(
    *,
    market: str,
    v3_root: Path,
    v4_root: Path,
    matrix_dir: Path,
    spec: dict[str, Any],
) -> dict[str, Any]:
    m = spec["markets"][market]
    symbol = str(m["symbol"])

    a = pd.read_parquet(
        v3_root / market.lower() / "historical_strategy_signal.parquet"
    )
    b = pd.read_parquet(
        v4_root / market.lower() / "historical_strategy_signal.parquet"
    )
    for x in (a, b):
        x["signal_ts"] = pd.to_datetime(
            x["signal_ts"], utc=True, errors="raise"
        )

    start = max(a["signal_ts"].min(), b["signal_ts"].min())
    end = min(a["signal_ts"].max(), b["signal_ts"].max())
    if pd.isna(start) or pd.isna(end) or start > end:
        raise RuntimeError(f"{market}: no common OOS window")

    prices = _load_prices(matrix_dir, market, symbol)
    prices = prices.loc[
        (prices["ts"] >= start) & (prices["ts"] <= end)
    ].copy()
    if prices.empty:
        raise RuntimeError(f"{market}: no prices in common window")

    out: dict[str, Any] = {
        "status": "READY",
        "start": start,
        "end": end,
        "market": market,
        "symbol": symbol,
        "variants": {},
    }

    for fraction in (0.10, 1.00):
        key = f"{int(fraction * 100)}pct"
        cfg = BacktestConfig(
            initial_cash=1_000_000.0,
            position_fraction=fraction,
            max_open_positions=1,
            commission_bps=float(spec.get("commission_bps", 5.0)),
            slippage_bps=float(spec.get("slippage_bps", 5.0)),
            max_hold_bars=int(m.get("max_hold_bars", 20)),
            allow_fractional=True,
        )

        pair: dict[str, Any] = {}
        for name, sig in (("V3", a), ("V4_MACRO", b)):
            s = sig.loc[
                (sig["signal_ts"] >= start)
                & (sig["signal_ts"] <= end),
                ["symbol", "signal_ts", "signal", "entry_allowed"],
            ].copy()
            pair[name] = run_backtest(s, prices, cfg).metrics

        v3ret = pair["V3"].get("total_return")
        v4ret = pair["V4_MACRO"].get("total_return")
        v3sh = pair["V3"].get("sharpe")
        v4sh = pair["V4_MACRO"].get("sharpe")
        pair["delta"] = {
            "total_return": (
                float(v4ret) - float(v3ret)
                if v3ret is not None and v4ret is not None
                else None
            ),
            "sharpe": (
                float(v4sh) - float(v3sh)
                if v3sh is not None and v4sh is not None
                else None
            ),
        }
        out["variants"][key] = pair

    return out


def main() -> int:
    args = parse_args()
    v3_root = Path(args.v3_root).expanduser()
    v4_root = Path(args.v4_root).expanduser()
    matrix_dir = Path(args.matrix_dir).expanduser()
    spec = json.loads(
        Path(args.spec).expanduser().read_text(encoding="utf-8")
    )

    status: dict[str, Any] = {
        "status": "READY",
        "markets": {},
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }

    for market in MARKETS:
        try:
            status["markets"][market] = compare_market(
                market=market,
                v3_root=v3_root,
                v4_root=v4_root,
                matrix_dir=matrix_dir,
                spec=spec,
            )
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
