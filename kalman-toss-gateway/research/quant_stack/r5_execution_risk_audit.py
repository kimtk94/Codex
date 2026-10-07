from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def metrics(returns: pd.Series, timestamps: pd.Series) -> dict:
    r = pd.Series(returns, dtype=float).fillna(0.0)
    wealth = (1.0 + r).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    years = max(
        (pd.Timestamp(timestamps.iloc[-1]) - pd.Timestamp(timestamps.iloc[0])).total_seconds()
        / (365.25 * 86400.0),
        1.0 / 365.25,
    )
    total = float(wealth.iloc[-1] - 1.0)
    cagr = float((1.0 + total) ** (1.0 / years) - 1.0) if total > -1 else -1.0
    return {"total_return": total, "cagr": cagr, "mdd": float(drawdown.min())}


def price_frame(panel_dir: Path, symbol: str, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if symbol in cache:
        return cache[symbol]
    path = panel_dir / f"{symbol}_1h_gap_aware.parquet"
    z = pd.read_parquet(path)
    time_col = "timestamp" if "timestamp" in z.columns else "candle_time_utc"
    z = z[["expected_seq", time_col, "open", "low", "close"]].copy()
    z = z.rename(columns={time_col: "timestamp"})
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True)
    cache[symbol] = z.set_index("expected_seq").sort_index()
    return cache[symbol]


def simulate_top1(
    common: pd.DataFrame,
    liquidity: dict,
    panel_dir: Path,
    *,
    stop_pct: float = -0.03,
    each_side_slippage_bps: float = 0.0,
    round_trip_cost_bps: float = 10.0,
    min_signal_dollar_volume: float = 0.0,
) -> tuple[dict, list[dict]]:
    cache: dict[str, pd.DataFrame] = {}
    slip = each_side_slippage_bps / 10000.0
    cost = round_trip_cost_bps / 10000.0
    returns: list[float] = []
    gaps: list[dict] = []
    eligible = 0
    intrabar_stops = 0

    for row in common.itertuples(index=False):
        key = (int(row.expected_seq), str(row.rank1_symbol))
        signal_dollar_volume = float(liquidity.get(key, 0.0) or 0.0)
        if signal_dollar_volume < min_signal_dollar_volume:
            returns.append(0.0)
            continue

        eligible += 1
        frame = price_frame(panel_dir, row.rank1_symbol, cache).loc[
            int(row.entry_expected_seq): int(row.actual_exit_seq)
        ]
        entry_seq = int(row.entry_expected_seq)
        exit_seq = int(row.actual_exit_seq)
        entry_reference = float(frame.loc[entry_seq, "open"])
        buy_price = entry_reference * (1.0 + slip)
        stop_level = entry_reference * (1.0 + stop_pct)
        exit_price = None

        for seq, bar in frame.iterrows():
            bar_open = float(bar["open"])
            bar_low = float(bar["low"])
            if int(seq) == entry_seq:
                if bar_low <= stop_level:
                    exit_price = stop_level * (1.0 - slip)
                    intrabar_stops += 1
                    break
                continue
            if bar_open <= stop_level:
                exit_price = bar_open * (1.0 - slip)
                gaps.append(
                    {
                        "symbol": row.rank1_symbol,
                        "signal_seq": int(row.expected_seq),
                        "exit_seq": int(seq),
                        "gap_return_vs_entry": bar_open / entry_reference - 1.0,
                    }
                )
                break
            if bar_low <= stop_level:
                exit_price = stop_level * (1.0 - slip)
                intrabar_stops += 1
                break

        if exit_price is None:
            exit_price = float(frame.loc[exit_seq, "close"]) * (1.0 - slip)
        returns.append(exit_price / buy_price - 1.0 - cost)

    result = metrics(pd.Series(returns), common["entry_timestamp"])
    result.update(
        {
            "eligible": int(eligible),
            "gap_stops": int(len(gaps)),
            "intrabar_stops": int(intrabar_stops),
            "worst_gap": min((x["gap_return_vs_entry"] for x in gaps), default=None),
        }
    )
    return result, gaps


def universe_audit(rankings: pd.DataFrame) -> dict:
    z = rankings[["timestamp", "symbol"]].copy()
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True)
    windows = {
        "2023H1": ("2023-01-01", "2023-07-01"),
        "2024": ("2024-01-01", "2025-01-01"),
        "2025": ("2025-01-01", "2026-01-01"),
        "2026YTD": ("2026-01-01", "2027-01-01"),
    }
    sets = {
        name: set(z.loc[(z.timestamp >= start) & (z.timestamp < end), "symbol"].astype(str))
        for name, (start, end) in windows.items()
    }
    base = sets["2023H1"]
    static = all(s == base for s in sets.values())
    return {
        "status": "STATIC_UNIVERSE_CONFIRMED" if static else "UNIVERSE_CHANGED",
        "total_unique_symbols": int(z["symbol"].nunique()),
        "windows": {
            name: {
                "count": len(s),
                "same_as_2023H1": s == base,
                "added_vs_2023H1": sorted(s - base),
                "missing_vs_2023H1": sorted(base - s),
            }
            for name, s in sets.items()
        },
        "survivorship_assessment": (
            "Historical point-in-time membership is not represented by this artifact; "
            "do not interpret the backtest as a market-wide survivorship-free result."
            if static
            else "Universe changes exist; membership provenance still requires validation."
        ),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R5.1 execution, stop, liquidity and universe risk audit")
    p.add_argument("--common-panel", type=Path, required=True)
    p.add_argument("--rankings", type=Path, required=True)
    p.add_argument("--locked-panel", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    common = pd.read_parquet(args.common_panel)
    rankings = pd.read_parquet(
        args.rankings,
        columns=["expected_seq", "timestamp", "symbol", "close", "volume"],
    )
    liquidity = (
        rankings.assign(dollar_volume=rankings["close"] * rankings["volume"])
        .set_index(["expected_seq", "symbol"])["dollar_volume"]
        .to_dict()
    )

    rows = []
    raw = common["rank1_raw_return"].astype(float)
    for slip in (0, 1, 2, 5, 10):
        s = slip / 10000.0
        stressed = (1.0 + raw) * (1.0 - s) / (1.0 + s) - 1.0 - 0.001
        row = metrics(stressed, common["entry_timestamp"])
        row.update({"scenario": f"FIXED4_{slip}bps_each_side", "eligible": len(common), "gap_stops": None, "intrabar_stops": None, "worst_gap": None})
        rows.append(row)

    all_gaps = []
    for slip in (0, 1, 2, 5, 10):
        result, gaps = simulate_top1(common, liquidity, args.locked_panel, each_side_slippage_bps=slip)
        result["scenario"] = f"STOP3_{slip}bps_each_side"
        rows.append(result)
        if slip == 2:
            all_gaps = gaps

    for threshold in (1e6, 2e6, 5e6, 10e6):
        result, _ = simulate_top1(
            common,
            liquidity,
            args.locked_panel,
            each_side_slippage_bps=2,
            min_signal_dollar_volume=threshold,
        )
        result["scenario"] = f"STOP3_2bps_DV{int(threshold / 1e6)}M"
        rows.append(result)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(rows)
    summary = summary[["scenario", "eligible", "total_return", "cagr", "mdd", "gap_stops", "intrabar_stops", "worst_gap"]]
    summary.to_csv(args.output_dir / "summary.csv", index=False)
    pd.DataFrame(all_gaps).sort_values("gap_return_vs_entry").to_csv(args.output_dir / "gap_stops.csv", index=False)
    (args.output_dir / "universe_audit.json").write_text(json.dumps(universe_audit(rankings), indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
