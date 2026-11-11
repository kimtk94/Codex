from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.quant_stack.prediction_market_leadlag_v0 import (
    align_asset,
    attach_us2y,
    build_event_hours,
    load_asset_history,
    load_us2y,
    parse_asset_arg,
)


HORIZONS = (1, 4, 7)


def cluster_bootstrap_ci(
    frame: pd.DataFrame,
    value_col: str,
    *,
    date_col: str,
    iterations: int = 1000,
    seed: int = 42,
) -> tuple[float | None, float | None]:
    x = frame[[date_col, value_col]].dropna().copy()
    if x.empty:
        return None, None
    x["event_date"] = pd.to_datetime(x[date_col], utc=True).dt.date
    dates = np.array(sorted(x["event_date"].unique()), dtype=object)
    if len(dates) < 3:
        return None, None
    groups = {d: x.loc[x["event_date"] == d, value_col].to_numpy() for d in dates}
    rng = np.random.default_rng(seed)
    vals = np.empty(iterations, dtype=float)
    for i in range(iterations):
        sampled = rng.choice(dates, size=len(dates), replace=True)
        arr = np.concatenate([groups[d] for d in sampled])
        vals[i] = float(np.mean(arr))
    lo, hi = np.quantile(vals, [0.025, 0.975])
    return float(lo), float(hi)


def cluster_signflip_p(
    frame: pd.DataFrame,
    value_col: str,
    *,
    date_col: str,
    iterations: int = 10000,
    seed: int = 42,
) -> tuple[float | None, float | None]:
    x = frame[[date_col, value_col]].dropna().copy()
    if x.empty:
        return None, None
    x["event_date"] = pd.to_datetime(x[date_col], utc=True).dt.date
    daily = x.groupby("event_date")[value_col].agg(["sum", "count", "mean"])
    if len(daily) < 3:
        return None, None

    observed = float(daily["sum"].sum() / daily["count"].sum())
    positive_date_rate = float((daily["mean"] > 0).mean())
    sums = daily["sum"].to_numpy(dtype=float)
    counts = daily["count"].to_numpy(dtype=float)
    n_dates = len(daily)

    if n_dates <= 16:
        total = 1 << n_dates
        masks = np.arange(total, dtype=np.uint64)[:, None]
        bits = (masks >> np.arange(n_dates, dtype=np.uint64)) & 1
        signs = np.where(bits == 1, 1.0, -1.0)
        null = (signs @ sums) / np.sum(counts)
    else:
        rng = np.random.default_rng(seed)
        signs = rng.choice(
            np.array([-1.0, 1.0]),
            size=(iterations, n_dates),
            replace=True,
        )
        null = (signs @ sums) / np.sum(counts)

    p = float((np.sum(np.abs(null) >= abs(observed)) + 1) / (len(null) + 1))
    return p, positive_date_rate


def benjamini_hochberg(pvalues: pd.Series) -> pd.Series:
    p = pd.to_numeric(pvalues, errors="coerce")
    q = pd.Series(np.nan, index=p.index, dtype=float)
    valid = p.dropna().sort_values()
    if valid.empty:
        return q

    m = len(valid)
    ranked = valid.to_numpy(dtype=float) * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    ranked = np.clip(ranked, 0.0, 1.0)
    q.loc[valid.index] = ranked
    return q


def summarize_group(
    frame: pd.DataFrame,
    *,
    threshold: float,
    symbol: str,
    group_type: str,
    group_name: str,
    bootstrap_iterations: int,
) -> list[dict]:
    out: list[dict] = []
    if frame.empty:
        return out

    event_col = "event_at" if "event_at" in frame.columns else "event_hour"
    for bars in HORIZONS:
        ret_col = f"fwd_return_{bars}bar"
        x = frame[[event_col, "event_score", ret_col]].dropna().copy()
        if x.empty:
            continue
        x["signed_return"] = np.sign(x["event_score"]) * x[ret_col]
        corr = (
            float(x["event_score"].corr(x[ret_col]))
            if len(x) >= 3 and x["event_score"].nunique() > 1 and x[ret_col].nunique() > 1
            else None
        )
        ci_lo, ci_hi = cluster_bootstrap_ci(
            x,
            "signed_return",
            date_col=event_col,
            iterations=bootstrap_iterations,
        )
        signflip_p, positive_date_rate = cluster_signflip_p(
            x,
            "signed_return",
            date_col=event_col,
            iterations=max(10000, bootstrap_iterations),
        )
        out.append(
            {
                "threshold": threshold,
                "symbol": symbol,
                "group_type": group_type,
                "group_name": group_name,
                "bars": bars,
                "n": int(len(x)),
                "unique_dates": int(pd.to_datetime(x[event_col], utc=True).dt.date.nunique()),
                "mean_signed_return": float(x["signed_return"].mean()),
                "median_signed_return": float(x["signed_return"].median()),
                "hit_rate": float((x["signed_return"] > 0).mean()),
                "positive_date_rate": positive_date_rate,
                "corr_event_score_return": corr,
                "bootstrap_ci_low": ci_lo,
                "bootstrap_ci_high": ci_hi,
                "cluster_signflip_p": signflip_p,
            }
        )
    return out


def build_matrix(
    prediction: pd.DataFrame,
    assets: dict[str, pd.DataFrame],
    rates: pd.DataFrame | None,
    *,
    thresholds: list[float],
    max_entry_lag_minutes: float,
    bootstrap_iterations: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    for threshold in thresholds:
        events = build_event_hours(prediction, min_abs_delta_1h=threshold)
        events = attach_us2y(events, rates)

        for symbol, asset in assets.items():
            aligned = align_asset(events, asset)
            if aligned.empty:
                continue
            aligned = aligned[
                aligned["entry_lag_minutes"].notna()
                & (aligned["entry_lag_minutes"] <= max_entry_lag_minutes)
            ].copy()
            if aligned.empty:
                continue

            groups: list[tuple[str, str, pd.DataFrame]] = [
                ("ALL", "ALL", aligned),
            ]
            for name, g in aligned.groupby("dominant_channel", dropna=False):
                groups.append(("CHANNEL", str(name), g))
            for name, g in aligned.groupby("dominant_theme", dropna=False):
                groups.append(("THEME", str(name), g))

            fed = aligned[
                aligned["dominant_channel"].isin(["FED_EASING", "FED_TIGHTENING"])
            ]
            if not fed.empty:
                groups.append(
                    (
                        "FED_CONFIRMATION",
                        "CONFIRMED",
                        fed[fed["us2y_confirmation"] == True],
                    )
                )
                groups.append(
                    (
                        "FED_CONFIRMATION",
                        "UNCONFIRMED",
                        fed[fed["us2y_confirmation"] == False],
                    )
                )

            for group_type, group_name, group in groups:
                rows.extend(
                    summarize_group(
                        group,
                        threshold=threshold,
                        symbol=symbol,
                        group_type=group_type,
                        group_name=group_name,
                        bootstrap_iterations=bootstrap_iterations,
                    )
                )

    matrix = pd.DataFrame(rows)
    if not matrix.empty:
        matrix["fdr_q"] = benjamini_hochberg(matrix["cluster_signflip_p"])
    return matrix


def promotion_candidates(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return matrix.copy()
    out = matrix.copy()
    out["candidate"] = (
        (out["n"] >= 20)
        & (out["unique_dates"] >= 8)
        & (out["hit_rate"] >= 0.55)
        & (out["positive_date_rate"].fillna(0.0) >= 0.60)
        & (out["mean_signed_return"] > 0)
        & (out["bootstrap_ci_low"].fillna(-1.0) > 0)
        & (out["fdr_q"].fillna(1.0) <= 0.10)
    )
    return out[out["candidate"]].sort_values(
        ["mean_signed_return", "n"], ascending=[False, False]
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prediction-market stratified lead/lag audit v0")
    p.add_argument("--prediction", required=True)
    p.add_argument("--asset", action="append", required=True, type=parse_asset_arg)
    p.add_argument("--us2y")
    p.add_argument("--thresholds", default="0.05,0.10,0.15")
    p.add_argument("--max-entry-lag-minutes", type=float, default=90.0)
    p.add_argument("--bootstrap-iterations", type=int, default=1000)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    prediction = pd.read_parquet(args.prediction)
    assets = {
        symbol: load_asset_history(path, symbol)
        for symbol, path in args.asset
    }
    rates = load_us2y(Path(args.us2y)) if args.us2y else None
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]

    matrix = build_matrix(
        prediction,
        assets,
        rates,
        thresholds=thresholds,
        max_entry_lag_minutes=args.max_entry_lag_minutes,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    candidates = promotion_candidates(matrix)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(out_dir / "stratified_matrix.csv", index=False)
    matrix.to_parquet(out_dir / "stratified_matrix.parquet", index=False)
    candidates.to_csv(out_dir / "promotion_candidates.csv", index=False)

    payload = {
        "status": "READY",
        "research_only": True,
        "thresholds": thresholds,
        "max_entry_lag_minutes": args.max_entry_lag_minutes,
        "bootstrap_iterations": args.bootstrap_iterations,
        "rows": int(len(matrix)),
        "promotion_candidate_rows": int(len(candidates)),
        "promotion_rule": {
            "n_min": 20,
            "unique_dates_min": 8,
            "hit_rate_min": 0.55,
            "positive_date_rate_min": 0.60,
            "mean_signed_return_gt": 0,
            "cluster_bootstrap_ci_low_gt": 0,
            "cluster_signflip_fdr_q_max": 0.10,
        },
        "production_promotion": False,
        "r51_mutated": False,
    }
    (out_dir / "stratified_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    if not candidates.empty:
        print("\nPROMOTION CANDIDATES")
        print(candidates.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
