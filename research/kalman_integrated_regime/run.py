#!/usr/bin/env python3
"""QLD integrated-regime, strictly historical, research-only experiment."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PRICE = ["qqq_r5", "qqq_r20", "qld_r5", "qqq_vol20", "qld_minus_2qqq"]
EXTRA = ["vix_lag1", "vix_r5_lag1", "hyg_lqd_r5_lag1",
         "tnx_lag1", "smh_spy_r20_lag1"]
MARKET = ["yf_vix", "yf_hyg", "yf_lqd", "yf_tnx", "yf_spy", "yf_smh"]
FEE = 0.001
TP = 0.03
SL = 0.03
HOLD = 4
TZ = "America/New_York"


def read_prices(path):
    d = pd.read_csv(path, parse_dates=["date_ny"]).sort_values("date_ny")
    needed = {"date_ny", "close_qqq", "close_qld"}
    if not needed.issubset(d.columns):
        raise ValueError("DAILY_MISSING_COLUMNS")
    if d.date_ny.isna().any() or d.date_ny.duplicated().any():
        raise ValueError("DAILY_DUPLICATE_OR_NULL_DATE")
    prices = d[["close_qqq", "close_qld"]].apply(pd.to_numeric, errors="raise")
    if ((prices.notna()) & (prices <= 0)).any().any():
        raise ValueError("DAILY_NONPOSITIVE_CLOSE")
    if not prices.notna().any().all():
        raise ValueError("DAILY_NO_VALID_PRICE_SERIES")
    d[["close_qqq", "close_qld"]] = prices
    d = d.set_index("date_ny")
    return d.loc["2024-01-01":"2026-12-31"].copy()


def read_market_zip(path):
    out = {}
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("schema") != "kalman-daily-market-research-bundle-v1":
            raise ValueError("MARKET_UNEXPECTED_MANIFEST")
        for key in MARKET:
            name = f"market/raw/yfinance/{key}.parquet"
            if name not in z.namelist():
                raise ValueError("MARKET_MISSING_" + key)
            d = pd.read_parquet(io.BytesIO(z.read(name)))
            if not {"timestamp", "close"}.issubset(d):
                raise ValueError("MARKET_BAD_SCHEMA_" + key)
            ts = pd.to_datetime(d.timestamp, utc=True)
            # Daily yfinance timestamps are session-date labels at UTC midnight.
            date = ts.dt.tz_localize(None).dt.normalize()
            s = pd.Series(pd.to_numeric(d.close, errors="coerce").to_numpy(),
                          index=pd.DatetimeIndex(date), name=key).sort_index()
            if s.index.duplicated().any() or (s.dropna() <= 0).any():
                raise ValueError("MARKET_BAD_DATES_OR_VALUES_" + key)
            out[key] = s
    return out


def build_features(daily, market):
    f = pd.DataFrame(index=daily.index)
    q = daily.close_qqq.astype(float)
    l = daily.close_qld.astype(float)
    f["qqq_r5"] = q.pct_change(5, fill_method=None)
    f["qqq_r20"] = q.pct_change(20, fill_method=None)
    f["qld_r5"] = l.pct_change(5, fill_method=None)
    f["qqq_vol20"] = np.log(q / q.shift()).rolling(20).std()
    f["qld_minus_2qqq"] = l.pct_change(fill_method=None) - 2*q.pct_change(fill_method=None)
    m = {k: market[k].reindex(f.index) for k in MARKET}
    f["vix_lag1"] = m["yf_vix"].shift(1)
    f["vix_r5_lag1"] = m["yf_vix"].pct_change(5, fill_method=None).shift(1)
    f["hyg_lqd_r5_lag1"] = (m["yf_hyg"].pct_change(5, fill_method=None)
                           - m["yf_lqd"].pct_change(5, fill_method=None)).shift(1)
    f["tnx_lag1"] = m["yf_tnx"].shift(1)
    f["smh_spy_r20_lag1"] = (m["yf_smh"].pct_change(20, fill_method=None)
                             - m["yf_spy"].pct_change(20, fill_method=None)).shift(1)
    return f.replace([np.inf, -np.inf], np.nan)


def read_15m(path):
    x = pd.read_parquet(path)
    needed = {"candle_time_utc", "open", "high", "low", "close", "unit_min"}
    if not needed.issubset(x.columns):
        raise ValueError("INTRADAY_BAD_SCHEMA")
    if "market" in x.columns:
        x = x.loc[x.market.astype(str).str.upper().eq("QLD")].copy()
    x = x.loc[pd.to_numeric(x.unit_min).eq(15)].copy()
    x["ts"] = pd.to_datetime(x.candle_time_utc, utc=True).dt.tz_convert(TZ)
    if x.ts.isna().any() or x.ts.duplicated().any():
        raise ValueError("INTRADAY_BAD_TIMESTAMP")
    ohlc = x[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(ohlc.to_numpy()).all() or (ohlc <= 0).any().any():
        raise ValueError("INTRADAY_BAD_PRICE")
    if (x.high < x[["open", "low", "close"]].max(axis=1)).any() or (
        x.low > x[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("INTRADAY_BAD_OHLC")
    return x.sort_values("ts").reset_index(drop=True)


def complete_sessions(x, session_dates):
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS")
    x = x.copy()
    # Normalize NY-local time, not UTC.
    x["session"] = pd.to_datetime(x.ts.dt.strftime("%Y-%m-%d"))
    groups = {k: g.reset_index(drop=True) for k, g in x.groupby("session")}
    complete, counts = {}, {"complete": 0, "missing": 0, "partial": 0, "extended_bars_ignored": 0, "missing_rth_slots_by_clock": {}, "partial_examples": []}
    for session in session_dates:
        date = pd.Timestamp(session)
        if not cal.is_session(date):
            counts["missing"] += 1
            continue
        g = groups.get(date)
        if g is None:
            counts["missing"] += 1
            continue
        op = cal.session_open(date).tz_convert(TZ)
        cl = cal.session_close(date).tz_convert(TZ)
        expect = pd.date_range(op, cl - pd.Timedelta(minutes=15), freq="15min")
        # Exclude premarket/afterhours before checking complete 09:30-16:00 RTH.
        rth = g.loc[g.ts.ge(op) & g.ts.lt(cl)].reset_index(drop=True)
        counts["extended_bars_ignored"] += len(g) - len(rth)
        # Never fill a missing RTH bar; its path-dependent barrier is unknown.
        if len(rth) != len(expect) or not pd.DatetimeIndex(rth.ts).equals(expect):
            counts["partial"] += 1
            absent = expect.difference(pd.DatetimeIndex(rth.ts))
            for ts in absent:
                slot = ts.strftime("%H:%M")
                counts["missing_rth_slots_by_clock"][slot] = counts["missing_rth_slots_by_clock"].get(slot, 0) + 1
            if len(counts["partial_examples"]) < 5:
                counts["partial_examples"].append({
                    "date": str(date.date()), "expected": len(expect),
                    "observed_rth": len(rth), "missing_rth": len(absent)})
            continue
        complete[date] = rth
        counts["complete"] += 1
    return complete, counts


def settle(bars, entry, fee=FEE, tp=TP, sl=SL):
    upper, lower = entry * (1 + tp), entry * (1 - sl)
    for day, frame in bars:
        for b in frame.itertuples(index=False):
            if b.open <= lower:
                px, reason = float(b.open), "SL_GAP"
            elif b.open >= upper:
                px, reason = float(b.open), "TP_GAP"
            elif b.low <= lower:
                px, reason = lower, "SL"  # both hit -> SL, conservative
            elif b.high >= upper:
                px, reason = upper, "TP"
            else:
                continue
            net = (px / entry) * (1 - fee) ** 2 - 1
            return day, px, reason, net
    day, frame = bars[-1]
    px = float(frame.iloc[-1].close)
    net = (px / entry) * (1 - fee) ** 2 - 1
    return day, px, "TIME", net


def label_events(dates, complete, fee=FEE):
    rows = []
    date_list = list(pd.DatetimeIndex(dates))
    for i, date in enumerate(date_list):
        future = date_list[i+1:i+1+HOLD]
        if len(future) != HOLD or any(t not in complete for t in future):
            continue
        entry = float(complete[future[0]].iloc[0].open)
        exit_date, px, reason, net = settle([(t, complete[t]) for t in future],
                                            entry, fee=fee)
        rows.append({"date": date, "entry_date": future[0],
                     "exit_date": exit_date, "entry": entry,
                     "exit": px, "reason": reason, "net_return": net,
                     "positive": int(net > 0)})
    return pd.DataFrame(rows)


def select_nonoverlap(rows):
    selected, last_exit = [], pd.Timestamp("1900-01-01")
    for item in rows.sort_values(["entry_date", "date"]).itertuples(index=False):
        if item.entry_date <= last_exit:
            continue
        selected.append(item._asdict())
        last_exit = item.exit_date
    return pd.DataFrame(selected, columns=rows.columns)


def metrics(rows, sessions):
    if rows.empty:
        return {"trades": 0, "return_pct": 0., "win_rate_pct": None,
                "mdd_daily_mark_pct": 0., "mean_trade_pct": None}
    capital = 1.
    path = []
    by_entry = {pd.Timestamp(r.entry_date): r for r in rows.itertuples(index=False)}
    active = None
    for day in sessions:
        if day in by_entry:
            active = by_entry[day]
            base = capital
        if active is not None:
            if active.exit_date == day:
                capital = base * (1 + active.net_return)
                active = None
            else:
                # Closed-session MTM uses the day close of valid 15m bars.
                capital = base * (1 - FEE) * float(sessions[day].iloc[-1].close) / active.entry
        path.append(capital)
    p = np.array([1.] + path)
    mdd = np.min(p / np.maximum.accumulate(p) - 1)
    returns = pd.to_numeric(rows.net_return)
    return {"trades": int(len(rows)),
            "return_pct": round(float(100 * (capital - 1)), 4),
            "win_rate_pct": round(float((returns > 0).mean() * 100), 4),
            "mdd_daily_mark_pct": round(float(mdd * 100), 4),
            "mean_trade_pct": round(float(returns.mean() * 100), 4)}


def annual_run(features, events, complete, test_year, min_train=80):
    test_begin = pd.Timestamp(f"{test_year}-01-01")
    test_end = pd.Timestamp(f"{test_year}-12-31")
    # Purge anything whose path-dependent label exits after train end.
    train = events.loc[events.exit_date < test_begin]
    test = events.loc[(events.date >= test_begin) & (events.date <= test_end)
                      & (events.exit_date <= test_end)].copy()
    if len(test) == 0:
        raise ValueError(f"YEAR_{test_year}_NO_USABLE_LABELS")
    # Identical samples for both arms: complete features, and valid 4-session label.
    feature_cols = PRICE + EXTRA
    eligible = features[feature_cols].notna().all(axis=1)
    train = train.loc[train.date.map(eligible).fillna(False)]
    test = test.loc[test.date.map(eligible).fillna(False)]
    if len(train) < min_train or train.positive.nunique() < 2:
        raise ValueError(f"YEAR_{test_year}_INSUFFICIENT_TRAIN:{len(train)}")
    if len(test) < 1:
        raise ValueError(f"YEAR_{test_year}_NO_COMMON_FEATURES")
    if train.exit_date.max() >= test_begin:
        raise AssertionError("TRAIN_LABEL_LEAKAGE")
    full_sessions = {d: complete[d] for d in sorted(complete)
                     if d >= test_begin and d <= test_end}
    output = {"year": test_year, "train_samples": int(len(train)),
              "test_samples": int(len(test)),
              "train_last_exit_date": str(train.exit_date.max().date()),
              "test_first_signal": str(test.date.min().date()),
              "test_last_signal": str(test.date.max().date()),
              "evaluation_status": "PARTIAL" if test.date.max() < test_end - pd.Timedelta(days=7) else "FULL_OR_NEAR_FULL",
              "models": {}}
    candidates = {}
    for name, cols in [("price_only", PRICE), ("integrated_regime", PRICE+EXTRA)]:
        model = make_pipeline(StandardScaler(),
                              LogisticRegression(C=1., class_weight="balanced",
                                                 max_iter=1000, random_state=42))
        model.fit(features.loc[train.date, cols], train.positive)
        preds = model.predict_proba(features.loc[test.date, cols])[:, 1]
        picked = test.loc[preds >= 0.5].copy()
        candidate = select_nonoverlap(picked)
        candidates[name] = candidate
        output["models"][name] = {
            "selection_threshold": 0.5,
            "predicted_signals": int(len(picked)),
            "nonoverlap": metrics(candidate, full_sessions)}
    baseline = select_nonoverlap(test)
    output["models"]["all_days_entry"] = {"nonoverlap": metrics(baseline, full_sessions)}
    return output, candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", required=True)
    ap.add_argument("--market-zip", required=True)
    ap.add_argument("--intraday", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    daily = read_prices(a.daily)
    market = read_market_zip(a.market_zip)
    f = build_features(daily, market)
    x = read_15m(a.intraday)
    complete, integrity = complete_sessions(x, daily.index)
    events = label_events(daily.index, complete)
    if events.empty:
        raise ValueError("NO_REAL_15M_4DAY_EVENTS")
    eligible = f[PRICE + EXTRA].notna().all(axis=1)
    diagnostics = {
        "intraday_first": str(x.ts.min()),
        "intraday_last": str(x.ts.max()),
        "complete_sessions": integrity,
        "complete_sessions_by_year": {str(y): sum(d.year == y for d in complete)
                                      for y in (2024, 2025, 2026)},
        "events_by_signal_year": {str(y): int((events.date.dt.year == y).sum())
                                  for y in (2024, 2025, 2026)},
        "market_price_complete_by_year": {
            str(y): int(((eligible.index.year == y) & eligible).sum())
            for y in (2024, 2025, 2026)
        },
        "eligible_labeled_by_year": {
            str(y): int(events.loc[events.date.dt.year == y, "date"].map(eligible).fillna(False).sum())
            for y in (2024, 2025, 2026)
        },
    }
    print("INPUT_DIAGNOSTICS " + json.dumps(diagnostics), flush=True)

    report = {"status": "RESEARCH_ONLY", "strategy": "QLD",
              "execution": "next NYSE session 09:30 NY 15m open",
              "barrier": {"tp": TP, "sl": SL, "hold_sessions": HOLD,
                          "fee_bps_each_side": int(FEE*10000),
                          "both_barriers_same_bar": "SL_FIRST"},
              "price_only_and_integrated_same_dates": True,
              "market_lag_sessions": 1, "fred_excluded": True,
              "usdkrw_excluded": True, "intraday_source": "Drive QLD_15m_raw.parquet",
              "no_execution_authority": True,
              "data_coverage": {"diagnostics": diagnostics,
                                "daily_first": str(daily.index.min().date()),
                                "daily_last": str(daily.index.max().date()),
                                "intraday_first": str(x.ts.min()),
                                "intraday_last": str(x.ts.max()),
                                "sessions": integrity,
                                "valid_signal_labels": int(len(events))},
              "yearly": {}}
    audit = []
    blockers = []
    for year in (2025, 2026):
        try:
            one, rows = annual_run(f, events, complete, year)
            one["status"] = "EVALUATED"
            report["yearly"][str(year)] = one
            for name, data in rows.items():
                if len(data):
                    cp = data.copy()
                    cp["model"] = name
                    cp["year"] = year
                    audit.append(cp)
        except ValueError as exc:
            reason = str(exc)
            if not reason.startswith(f"YEAR_{year}_"):
                raise
            report["yearly"][str(year)] = {"status": "HOLD", "reason": reason}
            blockers.append(reason)
    report["status"] = "HOLD_INSUFFICIENT_DATA" if blockers else "EVALUATED_RESEARCH_ONLY"
    report["blockers"] = blockers
    output = Path(a.out)
    output.mkdir(parents=True, exist_ok=True)
    (output/"summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    if audit:
        pd.concat(audit).to_csv(output/"trades_private.csv", index=False)
    print("RESEARCH_AGGREGATE " + json.dumps(report, ensure_ascii=False), flush=True)
    # Fail the historical job when data gates are unmet, while preserving the
    # machine-readable HOLD artifact for audit and follow-on data backfill.
    if blockers:
        raise SystemExit(2)
    

if __name__ == "__main__":
    main()
