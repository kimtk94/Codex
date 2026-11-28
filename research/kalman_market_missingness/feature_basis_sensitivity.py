"""Same-runtime paired-price sensitivity, metadata only; not a strategy backtest."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path

import exchange_calendars as xc
import numpy as np
import pandas as pd
import talib

from backfill_queue import validated_archives, frame_dates, PRICE_KEYS, PAIRED_SHARED, sha

VERSION = "kalman-price-basis-feature-sensitivity-v1"
EVALUATION_SESSIONS = 46
MIN_SESSIONS = 201
METRIC_TOL = 1e-8


def paired_window(old, new, key, asof):
    views = []
    for frame in (old, new):
        dates = frame_dates(frame, key)
        view = frame.loc[:, list(PRICE_KEYS)].apply(pd.to_numeric, errors="coerce")
        view.index = pd.DatetimeIndex(dates)
        views.append(view)
    a, b = views
    end = pd.Timestamp(asof)
    start = max(a.index.min(), b.index.min())
    cal = xc.get_calendar("XNYS")
    if start > end or not cal.is_session(end):
        raise ValueError("SENSITIVITY_INVALID_SESSION_WINDOW")
    idx = pd.DatetimeIndex(cal.sessions_in_range(start, end)).tz_localize(None)
    x, y = a.reindex(idx), b.reindex(idx)
    def valid(f):
        return (np.isfinite(f).all(axis=1) & (f > 0).all(axis=1)
                & (f.high >= f[["open", "close", "low"]].max(axis=1))
                & (f.low <= f[["open", "close", "high"]].min(axis=1)))
    ok = valid(x) & valid(y)
    bad = np.flatnonzero(~ok.to_numpy())
    # Never bridge a missing session; use only the uninterrupted common suffix.
    start_i = int(bad[-1]) + 1 if len(bad) else 0
    return x.iloc[start_i:], y.iloc[start_i:], int((~ok).sum())


def features(f):
    h,l,c = (f[k].to_numpy(dtype=float) for k in ("high","low","close"))
    _,_,hist = talib.MACD(c, fastperiod=12, slowperiod=26, signalperiod=9)
    return pd.DataFrame({"RSI14":talib.RSI(c,timeperiod=14),
                         "MACD_HIST":hist, "MACD_HIST_OVER_CLOSE":hist/c,
                         "ATR14":talib.ATR(h,l,c,timeperiod=14),
                         "NATR14":talib.NATR(h,l,c,timeperiod=14)},index=f.index)


def metrics(x,y,decision=None):
    pair = pd.concat([x.rename("a"),y.rename("b")],axis=1).tail(EVALUATION_SESSIONS)
    good = np.isfinite(pair).all(axis=1)
    p = pair.loc[good]
    delta = (p.a-p.b).abs()
    return {"expected_sessions":len(pair), "finite_pairs":len(p),
            "changed_pairs":int((delta>METRIC_TOL).sum()),
            "mean_abs_delta":float(delta.mean()) if len(p) else None,
            "max_abs_delta":float(delta.max()) if len(p) else None,
            "decision_disagreements":int((decision(p.a)!=decision(p.b)).sum())
                                     if decision is not None else None}


def rsi_zone(x):
    return np.select([x<30,x>70],[0,2],default=1)


def compare_asset(old,new,key,asof):
    a,b,invalid=paired_window(old,new,key,asof)
    row={"asset":key,"contiguous_paired_sessions":len(a),"invalid_or_absent_pairs":invalid,
         "status":"INSUFFICIENT_CONTIGUOUS_HISTORY_HOLD","metrics":{}}
    if len(a)<MIN_SESSIONS:
        return row, (a,b)
    x,y=features(a),features(b)
    decisions={"RSI14":rsi_zone,"MACD_HIST":lambda v:v>0,
               "MACD_HIST_OVER_CLOSE":lambda v:v>0}
    row["metrics"]={k:metrics(x[k],y[k],decisions.get(k)) for k in x}
    row["status"]="SAME_RUNTIME_SENSITIVITY_RESEARCH_HOLD"
    return row,(a,b)


def context_series(prices):
    # Exact prior-session lag of existing train.py context formulas. Reindex
    # only the common contiguous suffix; no fabricated trading dates.
    h,l,t,s = (prices[k].close for k in ("yf_hyg","yf_lqd","yf_tlt","yf_spy"))
    sma = s.rolling(200,min_periods=200).mean()
    return pd.DataFrame({
        "credit_mom5_lag":(h/l).pct_change(5,fill_method=None).shift(1),
        "tlt_mom5_lag":t.pct_change(5,fill_method=None).shift(1),
        "spy_above200_lag":(s>sma).astype(float).where(sma.notna()).shift(1),
    })


def compare_context(pairs):
    keys=("yf_hyg","yf_lqd","yf_tlt","yf_spy")
    if any(len(pairs[k][0])<MIN_SESSIONS for k in keys):
        return {"status":"INSUFFICIENT_CONTIGUOUS_CONTEXT_HOLD","metrics":{}}
    common=pairs[keys[0]][0].index
    for key in keys[1:]:
        common=common.intersection(pairs[key][0].index)
    if len(common)<MIN_SESSIONS:
        return {"status":"INSUFFICIENT_CONTIGUOUS_CONTEXT_HOLD","metrics":{}}
    a,b=(context_series({k:pairs[k][i].loc[common] for k in keys}) for i in (0,1))
    return {"status":"PAIRED_CONTEXT_SENSITIVITY_RESEARCH_HOLD",
            "contiguous_sessions":len(common),
            "metrics":{k:metrics(a[k],b[k],lambda v:v>0) for k in a}}


def build_report(macro_blob,daily_blob):
    mz,dz,_,ready,daily,am,ad=validated_archives(macro_blob,daily_blob)
    asof=ready["expected_last_completed_nyse_session"]
    rows,pairs=[],{}
    with mz,dz:
        for key in sorted(PAIRED_SHARED-{"yf_vix"}):
            row,pair=compare_asset(pd.read_parquet(BytesIO(mz.read(am[key]))),
                                   pd.read_parquet(BytesIO(dz.read(ad[key]))),key,asof)
            rows.append(row)
            pairs[key]=pair
    return {"version":VERSION,"status":"RESEARCH_HOLD","research_only":True,
            "production_writes":False,"live_execution":False,"strategy_promoted":False,
            "approved_backfill_rows":0,"source_sha256":sha(macro_blob),
            "reference_sha256":sha(daily_blob),"paired_asof":asof,
            "reference_asof":daily["data_expected_last_closed_xnys"],
            "talib_version":talib.__version__,"evaluation_sessions":EVALUATION_SESSIONS,
            "warmup_minimum_sessions":MIN_SESSIONS,
            "scope":"Two archived vintages; differences cannot be uniquely attributed to dividends.",
            "assets":rows,"context":compare_context(pairs)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--market-zip",required=True)
    p.add_argument("--daily20-zip",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    report=build_report(Path(args.market_zip).read_bytes(),Path(args.daily20_zip).read_bytes())
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    (out/"feature_basis_sensitivity.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("KALMAN_FEATURE_BASIS_SENSITIVITY_HOLD",json.dumps(report,allow_nan=False))


if __name__=="__main__":
    main()
