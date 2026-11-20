"""Annual expanding, purged next-open daily research. No production side effects."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from daily20 import feature_file, load_bars, market_file, write_json

HOLD = 4
COLUMNS = [
    "ret1", "ret5", "ret20", "sma20_gap", "sma50_gap", "sma200_gap",
    "volume_z20", "rsi14", "macd_hist", "adx14", "natr14", "roc10",
    "bb_pctb", "spy_mom5_lag", "spy_above200_lag", "qqq_mom5_lag",
    "smh_relative_lag", "credit_mom5_lag", "vix_lag", "tlt_mom5_lag",
    "gld_mom5_lag",
]


def context_frame(root):
    symbols = ["SPY", "QQQ", "SMH", "^VIX", "HYG", "LQD", "TLT", "GLD"]
    close = {s: load_bars(market_file(root, s))["close"] for s in symbols}
    spy = close["SPY"]
    # All macro/context features must be available no later than previous US session close.
    return pd.DataFrame({
        "spy_mom5_lag": spy.pct_change(5, fill_method=None).shift(1),
        "spy_above200_lag": (spy > spy.rolling(200).mean()).astype(float).shift(1),
        "qqq_mom5_lag": close["QQQ"].pct_change(5, fill_method=None).shift(1),
        "smh_relative_lag": (close["SMH"] / spy).pct_change(10, fill_method=None).shift(1),
        "credit_mom5_lag": (close["HYG"] / close["LQD"]).pct_change(5, fill_method=None).shift(1),
        "vix_lag": close["^VIX"].shift(1),
        "tlt_mom5_lag": close["TLT"].pct_change(5, fill_method=None).shift(1),
        "gld_mom5_lag": close["GLD"].pct_change(5, fill_method=None).shift(1),
    })


def feature_frame(symbol, market, features, context, cost_bps):
    x = load_bars(market_file(market, symbol))
    f = pd.read_parquet(feature_file(features, symbol))
    f["date"] = pd.to_datetime(f["timestamp"], utc=True).dt.tz_localize(None).dt.normalize()
    f = f.set_index("date").sort_index()
    c = x["close"].astype(float)
    v = x["volume"].astype(float)
    out = pd.DataFrame(index=x.index)
    for d in (1, 5, 20):
        out[f"ret{d}"] = c.pct_change(d, fill_method=None)
    for d in (20, 50, 200):
        out[f"sma{d}_gap"] = c / c.rolling(d).mean() - 1.0
    out["volume_z20"] = (v - v.rolling(20).mean()) / v.rolling(20).std().replace(0, np.nan)
    indicators = {
        "rsi14": "talib_v2_rsi14", "macd_hist": "talib_v2_macd_hist",
        "adx14": "talib_v2_adx14", "natr14": "talib_v2_natr14",
        "roc10": "talib_v2_roc10", "bb_pctb": "talib_v2_bb_pctb",
    }
    for name, source in indicators.items():
        out[name] = pd.to_numeric(f[source], errors="coerce").reindex(out.index)
    for name in context.columns:
        out[name] = context[name].reindex(out.index)
    out["entry_date"] = pd.Series(out.index, index=out.index).shift(-1)
    out["exit_date"] = pd.Series(out.index, index=out.index).shift(-HOLD)
    out["entry_open"] = x["open"].shift(-1)
    out["exit_close"] = c.shift(-HOLD)
    out["gross_return"] = out["exit_close"] / out["entry_open"] - 1
    out["net_return"] = out["gross_return"] - cost_bps / 10000.0
    return out.replace([np.inf, -np.inf], np.nan)


def eligible_row(row):
    return bool(row["spy_above200_lag"] >= 0.5 and row["vix_lag"] <= 35.0)


def nonoverlap(candidates, strategy):
    records = []
    last_exit = pd.Timestamp("1900-01-01")
    for dt, r in candidates.sort_index().iterrows():
        if dt <= last_exit or pd.isna(r["entry_date"]) or pd.isna(r["exit_date"]):
            continue
        records.append({
            "strategy": strategy, "signal_date": dt.date().isoformat(),
            "entry_date": r["entry_date"].date().isoformat(),
            "exit_date": r["exit_date"].date().isoformat(),
            "gross_return": float(r["gross_return"]), "net_return": float(r["net_return"]),
            "regime": "BULL" if r["spy_above200_lag"] >= 0.5 else "BEAR",
            "probability": float(r["prob"]) if strategy == "LOGISTIC" else None,
        })
        last_exit = r["exit_date"]
    return records


def model():
    # Fixed hyperparameters. No tuning or model selection against test-year data.
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
                         StandardScaler(),
                         LogisticRegression(C=0.2, class_weight="balanced",
                                            random_state=42, max_iter=500))


def model_split(df, year):
    """Purge any training label realized on or after test year's start."""
    boundary = pd.Timestamp(f"{year}-01-01")
    train = df[(df.index < boundary) & (df["exit_date"] < boundary) & df["net_return"].notna()]
    test = df[(df.index.year == year) & df["net_return"].notna()]
    return train, test


def model_year(df, year):
    train, test = model_split(df, year)
    if len(test) < 10 or len(train) < 252 or (train["net_return"] > 0).nunique() < 2:
        return None, None, {"year": year, "status": "INSUFFICIENT_DATA",
                            "train_rows": len(train), "test_rows": len(test)}
    fitted = model()
    fitted.fit(train[COLUMNS], (train["net_return"] > 0).astype(int))
    test = test.copy()
    test["prob"] = fitted.predict_proba(test[COLUMNS])[:, 1]
    return fitted, test, {"year": year, "status": "OOS_EVALUATED",
                          "train_rows": len(train), "test_rows": len(test)}


def research(spec, market, features, out):
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    context = context_frame(market)
    all_trades, scores, symbols_report = [], [], {}
    for symbol in spec["core"]:
        frame = feature_frame(symbol, market, features, context, spec["round_trip_cost_bps"])
        ml_candidates, rule_candidates, years = [], [], []
        latest_fitted = None
        for year in range(spec["first_test_year"], datetime.now(timezone.utc).year + 1):
            fitted, test, year_report = model_year(frame, year)
            years.append(year_report)
            if test is None:
                continue
            allowed = (test["spy_above200_lag"] >= 0.5) & (test["vix_lag"] <= 35.0)
            ml_candidates.append(test[allowed & (test["prob"] >= spec["probability_threshold"])])
            # Predeclared benchmark rule; never tune thresholds on these OOS years.
            rule = allowed & (test["sma50_gap"] > 0) & (test["macd_hist"] > 0) & test["rsi14"].between(45, 70)
            rule_candidates.append(test[rule])
            latest_fitted = fitted
        summary = {"annual_folds": years, "strategies": {}}
        for strategy, parts in (("LOGISTIC", ml_candidates), ("TREND_RULE", rule_candidates)):
            trades = nonoverlap(pd.concat(parts), strategy) if parts else []
            all_trades.extend({"symbol": symbol, **trade} for trade in trades)
            vals = [t["net_return"] for t in trades]
            summary["strategies"][strategy] = {
                "n_trades": len(vals),
                "mean_net_return": float(np.mean(vals)) if vals else None,
                "median_net_return": float(np.median(vals)) if vals else None,
                "win_rate": float(np.mean(np.array(vals) > 0)) if vals else None,
            }
        symbols_report[symbol] = summary
        if latest_fitted is not None:
            latest = frame.iloc[[-1]]
            prob = float(latest_fitted.predict_proba(latest[COLUMNS])[:, 1][0])
            permit = eligible_row(latest.iloc[0]) and prob >= spec["probability_threshold"]
            scores.append({"symbol": symbol, "signal_after_close": str(latest.index[-1].date()),
                           "logistic_prob_positive_net": prob,
                           "research_candidate": permit, "not_order": True,
                           "shadow_only": symbol in spec["high_risk_shadow_only"]})
    pd.DataFrame(all_trades).to_csv(directory / "oos_trades.csv", index=False)
    pd.DataFrame(scores).to_csv(directory / "latest_research_scores.csv", index=False)
    report = {"version": spec["version"], "research_only": True, "live_execution": False,
              "asof_policy": "completed_daily_close", "entry": "next_session_open",
              "exit": "fourth_next_session_close", "model": "fixed-parameter_logistic",
              "benchmark": "fixed-parameter_trend_rule", "round_trip_cost_bps": spec["round_trip_cost_bps"],
              "fixed_universe_selection_bias": True, "annual_label_purge_sessions": HOLD,
              "portfolio_level_mdd_available": False, "total_oos_trades": len(all_trades),
              "latest_score_count": len(scores), "results": symbols_report}
    write_json(directory / "summary.json", report)
    if len(scores) != 20:
        raise RuntimeError(f"INCOMPLETE_SCORES {len(scores)}/20; do not promote outputs")
    return report
