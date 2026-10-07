from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

STOP = -0.03
TAKE = 0.20
EMPIRICAL_COST_BPS = 36.59673953005761
COSTS = (36.59673953005761, 45.0, 50.0, 60.0)


def panel_path(root: Path, symbol: str) -> Path:
    return root / f"{str(symbol).upper().replace('.', '-')}_1h_gap_aware.parquet"


def load_panel(root: Path, symbol: str, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    key = str(symbol).upper()
    if key in cache:
        return cache[key]
    p = panel_path(root, key)
    if not p.is_file():
        cache[key] = pd.DataFrame()
        return cache[key]
    z = pd.read_parquet(
        p,
        columns=[
            "expected_seq", "open", "high", "low", "close",
            "session_date", "session_bucket", "candle_time_utc",
        ],
    )
    for c in ["open", "high", "low", "close"]:
        z[c] = pd.to_numeric(z[c], errors="coerce")
    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce").astype("Int64")
    z["candle_time_utc"] = pd.to_datetime(z["candle_time_utc"], utc=True, errors="coerce")
    z = (
        z.dropna(subset=["expected_seq", "open", "high", "low", "close"])
        .drop_duplicates("expected_seq", keep="last")
        .set_index("expected_seq")
        .sort_index()
    )
    cache[key] = z
    return z


def simulate_one(frame: pd.DataFrame, row, *, stop: bool, friday_flat: bool) -> dict:
    entry_seq = int(row.entry_expected_seq)
    exit_seq = int(row.exit_expected_seq)
    expected = list(range(entry_seq, exit_seq + 1))
    path = frame.reindex(expected)
    complete = bool(path[["open", "high", "low", "close"]].notna().all(axis=1).all())
    observed_bars = int(path["close"].notna().sum())
    if observed_bars == 0 or entry_seq not in frame.index:
        return {
            "path_complete": False,
            "observed_bars": observed_bars,
            "exit_reason": "NO_PATH",
            "policy_raw_return": np.nan,
            "policy_exit_seq": None,
        }

    entry = float(row.entry_price)
    stop_px = entry * (1.0 + STOP)
    take_px = entry * (1.0 + TAKE)
    valid = path.dropna(subset=["open", "high", "low", "close"])

    for seq, bar in valid.iterrows():
        o = float(bar.open)
        hi = float(bar.high)
        lo = float(bar.low)

        if stop:
            stop_touch = lo <= stop_px
            take_touch = hi >= take_px
            # Conservative ambiguity contract: stop wins if both touched in one 1H bar.
            if stop_touch:
                px = o if o <= stop_px else stop_px
                return {
                    "path_complete": complete,
                    "observed_bars": observed_bars,
                    "exit_reason": "STOP_GAP" if o <= stop_px else "STOP_3PCT",
                    "policy_raw_return": px / entry - 1.0,
                    "policy_exit_seq": int(seq),
                }
            if take_touch:
                px = o if o >= take_px else take_px
                return {
                    "path_complete": complete,
                    "observed_bars": observed_bars,
                    "exit_reason": "TAKE_GAP" if o >= take_px else "TAKE_20PCT",
                    "policy_raw_return": px / entry - 1.0,
                    "policy_exit_seq": int(seq),
                }

        if friday_flat:
            day = pd.Timestamp(str(bar.session_date)).date()
            if day.weekday() == 4 and int(bar.session_bucket) == 5:
                px = float(bar.close)
                return {
                    "path_complete": complete,
                    "observed_bars": observed_bars,
                    "exit_reason": "FRIDAY_FLAT",
                    "policy_raw_return": px / entry - 1.0,
                    "policy_exit_seq": int(seq),
                }

    if exit_seq in frame.index:
        px = float(frame.loc[exit_seq, "close"])
        return {
            "path_complete": complete,
            "observed_bars": observed_bars,
            "exit_reason": "HORIZON_20",
            "policy_raw_return": px / entry - 1.0,
            "policy_exit_seq": exit_seq,
        }
    return {
        "path_complete": complete,
        "observed_bars": observed_bars,
        "exit_reason": "HORIZON_MISSING",
        "policy_raw_return": np.nan,
        "policy_exit_seq": None,
    }


def metrics(z: pd.DataFrame, cost_bps: float) -> dict:
    q = z[z["policy_raw_return"].notna()].copy()
    if q.empty:
        return {"trades": 0}
    r = q["policy_raw_return"].astype(float) - cost_bps / 10000.0
    wealth = (1 + r).cumprod()
    dd = wealth / wealth.cummax() - 1
    start = pd.to_datetime(q.iloc[0]["timestamp"], utc=True)
    end = pd.to_datetime(q.iloc[-1]["timestamp"], utc=True)
    years = max((end - start).total_seconds() / (365.25 * 86400), 1 / 365.25)
    total = float(wealth.iloc[-1] - 1)
    cagr = float((1 + total) ** (1 / years) - 1) if total > -1 else -1.0
    return {
        "trades": int(len(q)),
        "total_return": total,
        "cagr": cagr,
        "max_drawdown": float(dd.min()),
        "mean_net_return": float(r.mean()),
        "median_net_return": float(r.median()),
        "win_rate": float((r > 0).mean()),
        "path_complete_rate": float(q["path_complete"].mean()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--panel-root", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    ledger = pd.read_parquet(args.ledger)
    ledger["timestamp"] = pd.to_datetime(ledger["timestamp"], utc=True, errors="coerce")
    # The ledger is already non-overlapping. Evaluate only PIT-conservative policies,
    # which are the stricter universe benchmark.
    ledger = ledger[ledger["universe"].eq("PIT_CONSERVATIVE")].copy()

    policies = {
        "HOLD20": (False, False),
        "STOP3_TAKE20": (True, False),
        "STOP3_TAKE20_FRIDAY_FLAT": (True, True),
    }
    cache: dict[str, pd.DataFrame] = {}
    detail_parts = []
    summary = []
    yearly = []

    keys = ["candidate", "variant"]
    for key, trades in ledger.groupby(keys, sort=False):
        candidate, variant = key
        for policy, (use_stop, use_friday) in policies.items():
            rows = []
            for r in trades.sort_values("timestamp").itertuples(index=False):
                frame = load_panel(args.panel_root, r.symbol, cache)
                result = simulate_one(frame, r, stop=use_stop, friday_flat=use_friday)
                rows.append({**r._asdict(), "exit_policy": policy, **result})
            z = pd.DataFrame(rows)
            detail_parts.append(z)
            for cost in COSTS:
                m = metrics(z, cost)
                reason_counts = z["exit_reason"].value_counts(dropna=False).to_dict()
                summary.append({
                    "candidate": candidate,
                    "variant": variant,
                    "exit_policy": policy,
                    "cost_bps": cost,
                    **m,
                    "exit_reason_counts": json.dumps(reason_counts, sort_keys=True),
                })
                zz = z[z["policy_raw_return"].notna()].copy()
                zz["year"] = zz["timestamp"].dt.year
                for year, g in zz.groupby("year"):
                    mm = metrics(g, cost)
                    yearly.append({
                        "candidate": candidate,
                        "variant": variant,
                        "exit_policy": policy,
                        "cost_bps": cost,
                        "year": int(year),
                        **mm,
                    })

    detail = pd.concat(detail_parts, ignore_index=True) if detail_parts else pd.DataFrame()
    summary_df = pd.DataFrame(summary)
    yearly_df = pd.DataFrame(yearly)
    detail.to_parquet(args.output_dir / "exit_policy_trades.parquet", index=False)
    summary_df.to_csv(args.output_dir / "exit_policy_summary.csv", index=False)
    yearly_df.to_csv(args.output_dir / "exit_policy_yearly.csv", index=False)

    empirical = summary_df[np.isclose(summary_df["cost_bps"], EMPIRICAL_COST_BPS)].copy()
    status = {
        "schema_version": "r5-2-exit-policy-stress-v1",
        "status": "COMPLETE",
        "research_only": True,
        "important_limitations": [
            "Hourly OHLC stop/take replay cannot observe the exact 5-minute watcher path.",
            "Same-bar stop/take ambiguity is resolved conservatively in favor of stop.",
            "Friday-flat is approximated as session_bucket=5 close, matching the last canonical fractional bar.",
            "Early exits do not free capacity for another trade; original non-overlap slots remain reserved.",
        ],
        "empirical_cost_bps": EMPIRICAL_COST_BPS,
        "top_empirical": empirical.sort_values(["cagr", "max_drawdown"], ascending=[False, False]).head(20).replace({np.nan: None}).to_dict(orient="records"),
    }
    (args.output_dir / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
