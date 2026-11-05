#!/usr/bin/env python3
"""100 train-only block-bootstrap fits of fixed QLD research models.

Repeated fits quantify sensitivity to training samples. They are NOT 100
independent out-of-sample market trials or a hyperparameter search.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.kalman_integrated_regime import run as base


def draw_training_blocks(n: int, block_size: int, rng: np.random.Generator) -> np.ndarray:
    """Sample contiguous blocks with replacement *only* among training events."""
    if n < 2 or block_size < 1:
        raise ValueError("INVALID_BOOTSTRAP_INPUT")
    width = min(block_size, n)
    indices = []
    while len(indices) < n:
        start = int(rng.integers(0, n - width + 1))
        indices.extend(range(start, start + width))
    result = np.asarray(indices[:n], dtype=int)
    if result.size != n or result.min() < 0 or result.max() >= n:
        raise AssertionError("BOOTSTRAP_OUT_OF_RANGE")
    return result


def quantiles(values):
    vals = np.asarray(values, dtype=float)
    if not len(vals) or not np.isfinite(vals).all():
        raise ValueError("BAD_METRIC_REPLICATES")
    return {k: round(float(v), 5) for k, v in zip(
        ("p05", "median", "p95"), np.quantile(vals, (0.05, 0.50, 0.95)))}


def regime_attribution(trades, features, thresholds):
    """Regime labels use exclusively train-year VIX terciles."""
    results = {}
    if trades.empty:
        return {s: {"trades": 0, "mean_trade_pct": None, "win_rate_pct": None}
                for s in ("LOW_VIX", "MID_VIX", "HIGH_VIX")}
    t = trades.copy()
    t["vix"] = features.loc[pd.DatetimeIndex(t.date), "vix_lag1"].to_numpy()
    t["regime"] = pd.cut(t.vix, bins=[-np.inf, thresholds[0], thresholds[1], np.inf],
                         labels=["LOW_VIX", "MID_VIX", "HIGH_VIX"], include_lowest=True)
    for category in ("LOW_VIX", "MID_VIX", "HIGH_VIX"):
        sub = t.loc[t.regime.eq(category)]
        results[category] = {"trades": int(len(sub)),
                             "mean_trade_pct": round(float(100 * sub.net_return.mean()), 4) if len(sub) else None,
                             "win_rate_pct": round(float(100 * (sub.net_return > 0).mean()), 4) if len(sub) else None}
    return results


def evaluate_year(features, events, complete, year, repeats=100, block_size=10, seed=20261031):
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31")
    train = events.loc[events.exit_date < start].sort_values("date").copy()
    test = events.loc[(events.date >= start) & (events.exit_date <= end)].sort_values("date").copy()
    eligible = features[base.PRICE + base.EXTRA].notna().all(axis=1)
    train = train.loc[train.date.map(eligible).fillna(False)].reset_index(drop=True)
    test = test.loc[test.date.map(eligible).fillna(False)].reset_index(drop=True)
    if len(train) < 80 or train.positive.nunique() < 2 or not len(test):
        raise ValueError(f"YEAR_{year}_TRAIN_OR_TEST_INVALID")
    assert train.exit_date.max() < start and train.date.max() < start
    assert test.date.min() >= start and test.date.max() <= end
    sessions = {date: complete[date] for date in sorted(complete) if start <= date <= end}
    train_vix = features.loc[train.date, "vix_lag1"].dropna().to_numpy()
    terciles = [float(v) for v in np.quantile(train_vix, (1/3, 2/3))]
    if terciles[0] >= terciles[1]:
        raise ValueError(f"YEAR_{year}_VIX_REGIME_COLLAPSED")
    rng = np.random.default_rng(seed + year)
    samples = []
    for rep in range(repeats):
        # One shared bootstrap draw per repetition = paired models.
        for attempt in range(50):
            positions = draw_training_blocks(len(train), block_size, rng)
            sampled = train.iloc[positions]
            if sampled.positive.nunique() == 2:
                break
        else:
            raise ValueError(f"YEAR_{year}_BOOTSTRAP_ONE_CLASS")
        outcomes = {"repeat": rep + 1,
                    "training_unique_fraction": float(np.unique(positions).size / len(train))}
        for name, cols in (("price_only", base.PRICE),
                           ("integrated_regime", base.PRICE + base.EXTRA)):
            model = make_pipeline(StandardScaler(),
                                  LogisticRegression(C=1.0, class_weight="balanced",
                                                     max_iter=1000, random_state=seed + rep))
            model.fit(features.loc[sampled.date, cols], sampled.positive)
            proba = model.predict_proba(features.loc[test.date, cols])[:, 1]
            picked = test.loc[proba >= 0.50].copy()
            chosen = base.select_nonoverlap(picked)
            result = base.metrics(chosen, sessions)
            outcomes[name] = {
                "return_pct": result["return_pct"], "trades": result["trades"],
                "win_rate_pct": result["win_rate_pct"] if result["win_rate_pct"] is not None else 0.,
                "mdd_daily_mark_pct": result["mdd_daily_mark_pct"],
                "predicted_signals": len(picked),
                "regimes": regime_attribution(chosen, features, terciles)
            }
        outcomes["integrated_minus_price_return_pct_points"] = (
            outcomes["integrated_regime"]["return_pct"] - outcomes["price_only"]["return_pct"])
        samples.append(outcomes)
    summary = {
        "year": year, "retraining_repeats": repeats,
        "train_samples": int(len(train)), "fixed_test_samples": int(len(test)),
        "train_last_exit": str(train.exit_date.max().date()),
        "test_first_signal": str(test.date.min().date()),
        "test_last_signal": str(test.date.max().date()),
        "block_size_train_events": block_size,
        "vix_regime_terciles_from_train_only": [round(v, 5) for v in terciles],
        "mean_training_unique_fraction": round(float(np.mean([x["training_unique_fraction"] for x in samples])), 4),
        "models": {},
        "paired_integrated_minus_price_return_pct_points":
            quantiles([x["integrated_minus_price_return_pct_points"] for x in samples]),
        "integrated_beats_price_fraction": round(
            sum(x["integrated_minus_price_return_pct_points"] > 0 for x in samples) / repeats, 4)
    }
    for name in ("price_only", "integrated_regime"):
        arr = [x[name] for x in samples]
        regimes = {}
        for label in ("LOW_VIX", "MID_VIX", "HIGH_VIX"):
            counts = [a["regimes"][label]["trades"] for a in arr]
            means = [a["regimes"][label]["mean_trade_pct"] for a in arr
                     if a["regimes"][label]["mean_trade_pct"] is not None]
            regimes[label] = {
                "trades_per_fit": quantiles(counts),
                "mean_trade_pct_across_fits": quantiles(means) if means else None,
                "fraction_of_fits_with_trades": round(sum(v > 0 for v in counts) / repeats, 4)}
        summary["models"][name] = {
            "return_pct": quantiles([a["return_pct"] for a in arr]),
            "mdd_daily_mark_pct": quantiles([a["mdd_daily_mark_pct"] for a in arr]),
            "trades": quantiles([a["trades"] for a in arr]),
            "positive_return_fraction": round(sum(a["return_pct"] > 0 for a in arr) / repeats, 4),
            "regimes": regimes}
    return summary


def compare_daily(sip_daily, legacy_daily):
    sip = pd.read_csv(sip_daily, parse_dates=["date_ny"]).set_index("date_ny")
    old = pd.read_csv(legacy_daily, parse_dates=["date_ny"]).set_index("date_ny")
    dates = sip.index.intersection(old.index)
    out = {"overlap_sessions": int(len(dates)),
           "legacy_last_date": str(old.index.max().date()),
           "sip_last_date": str(sip.index.max().date()),
           "comparison": {},
           "caution": "Adjusted SIP versus legacy vendor close may differ by dividends or split treatment; deviations must be investigated before trading."}
    if len(dates) < 100:
        out["status"] = "HOLD_FEW_OVERLAP"
        return out
    for sym in ("qld", "qqq"):
        a = sip.loc[dates, f"close_{sym}"].astype(float)
        b = old.loc[dates, f"close_{sym}"].astype(float)
        valid = a.notna() & b.notna() & b.gt(0)
        delta = (a.loc[valid] / b.loc[valid] - 1).abs()
        out["comparison"][sym.upper()] = {
            "matched_sessions": int(valid.sum()),
            "median_abs_relative_diff_pct": round(float(delta.median() * 100), 5),
            "p95_abs_relative_diff_pct": round(float(delta.quantile(.95) * 100), 5),
            "max_abs_relative_diff_pct": round(float(delta.max() * 100), 5),
            "sessions_above_0p5pct": int((delta > .005).sum()),
            "max_difference_date": str(delta.idxmax().date()) if len(delta) else None}
    out["status"] = ("CHECK_ADJUSTMENT_OR_VENDOR"
                     if any(v["sessions_above_0p5pct"] for v in out["comparison"].values())
                     else "CLOSE_MATCH_WITHIN_HALF_PERCENT")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--daily", required=True)
    p.add_argument("--legacy-daily", required=True)
    p.add_argument("--market-zip", required=True)
    p.add_argument("--intraday", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--repeats", type=int, default=100)
    p.add_argument("--block-size", type=int, default=10)
    args = p.parse_args()
    if args.repeats != 100:
        raise ValueError("REQUIRES_EXACTLY_100_TRAINING_REPEATS")
    prices = base.read_prices(args.daily)
    features = base.build_features(prices, base.read_market_zip(args.market_zip))
    candles = base.read_15m(args.intraday)
    complete, coverage = base.complete_sessions(candles, prices.index)
    events = base.label_events(prices.index, complete)
    comparison = compare_daily(args.daily, args.legacy_daily)
    report = {
        "status": "EVALUATED_RESEARCH_ONLY_HOLD_LIVE",
        "repeated_training_100": True,
        "training_scheme": "TRAIN_ONLY_MOVING_BLOCK_BOOTSTRAP_WITH_REPLACEMENT",
        "block_size": args.block_size, "n_repetitions": args.repeats,
        "retrain_each_year": True,
        "held_out_years": [2025, 2026],
        "same_fixed_test_dates_between_models": True,
        "same_train_bootstrap_draw_between_models": True,
        "no_hyperparameter_or_threshold_tuning_on_test": True,
        "fixed_selection_threshold": .5,
        "not_independent_OOS_trials": True,
        "not_a_formal_statistical_confidence_interval": True,
        "price_source_comparison": comparison,
        "complete_rth_sessions": coverage["complete"],
        "yearly": {},
        "live_modified": False,
    }
    for year in (2025, 2026):
        report["yearly"][str(year)] = evaluate_year(
            features, events, complete, year, args.repeats, args.block_size)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "retrain_100_summary.json").write_text(json.dumps(
        report, ensure_ascii=False, indent=2) + "\n")
    print("RETRAIN_100_AGGREGATE " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
