#!/usr/bin/env python3
"""Bounded private Alpaca SIP 15m historical multi-symbol OHLCV research backfill.

Five preapproved US stocks/ETFs only. Derived *aggregate* QA artifacts can go
to GitHub Actions; raw SIP bars, provider credentials and unadjusted prints
must never be uploaded as an Action artifact or committed.

A session without every 15-minute RTH bar is missing and cannot be used to
train a volume model. Full raw bars only live inside ephemeral runner.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests

from research.kalman_integrated_regime.us_multisymbol_microstructure import (
    approved_us_symbols, select_symbols, symbol_volume_features,
)
from research.kalman_integrated_regime.sip_backfill import month_ranges

ENDPOINT="https://data.alpaca.markets/v2/stocks/bars"
MAX_PAGE_BUDGET=850


class DownloadError(RuntimeError):
    pass


def get_months(session, symbols, start, end, key, secret,
               max_pages_per_month=25):
    rows=[]
    pages=0
    months=0
    for left,right in month_ranges(start,end):
        months+=1
        seen=set()
        token=None
        for _ in range(max_pages_per_month):
            query={"symbols":",".join(symbols),"timeframe":"15Min",
                   "start":left.strftime("%Y-%m-%dT00:00:00Z"),
                   "end":(right-pd.Timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "adjustment":"all","feed":"sip","limit":10000,
                   "sort":"asc"}
            if token:
                query["page_token"]=token
            response=None
            for retry in range(3):
                try:
                    response=session.get(ENDPOINT,params=query,
                        headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret},
                        timeout=35)
                except requests.RequestException:
                    if retry==2:
                        raise DownloadError("NETWORK_FAIL")
                    time.sleep(2*(retry+1))
                    continue
                if response.status_code in (429,500,502,503,504) and retry<2:
                    time.sleep(2*(retry+1))
                    continue
                break
            if response is None or response.status_code!=200:
                raise DownloadError("SIP_HTTP_"+str(getattr(response,"status_code","UNKNOWN")))
            try:
                data=response.json()
            except ValueError:
                raise DownloadError("SIP_INVALID_JSON")
            if not isinstance(data,dict) or not isinstance(data.get("bars"),dict):
                raise DownloadError("SIP_INVALID_SCHEMA")
            for symbol in symbols:
                points=data["bars"].get(symbol,[])
                if not isinstance(points,list):
                    raise DownloadError("SIP_BAD_SYMBOL_SCHEMA")
                for bar in points:
                    if not isinstance(bar,dict):
                        raise DownloadError("SIP_BAD_BAR_OBJECT")
                    rows.append({"market":symbol,"candle_time_utc":bar.get("t"),
                                 "unit_min":15,"open":bar.get("o"),
                                 "high":bar.get("h"),"low":bar.get("l"),
                                 "close":bar.get("c"),"volume":bar.get("v"),
                                 "trade_count":bar.get("n"),"vwap":bar.get("vw")})
            pages+=1
            if pages>MAX_PAGE_BUDGET:
                raise DownloadError(f"PAGE_BUDGET_EXCEEDED:month={left.date()}:pages={pages}:cap={MAX_PAGE_BUDGET}")
            token=data.get("next_page_token")
            if token is None:
                break
            if token in seen:
                raise DownloadError("SIP_REPEAT_PAGINATION_CURSOR")
            seen.add(token)
        else:
            raise DownloadError(f"SIP_MONTH_TRUNCATED:month={left.date()}:per_month_cap={max_pages_per_month}:global_pages={pages}")
        print("SIP_MONTH_PROGRESS "+json.dumps({"month":str(left.date()),"global_pages":pages,"total_rows":len(rows)}),flush=True)
    if not rows:
        raise DownloadError("SIP_NO_BARS")
    frame=pd.DataFrame(rows)
    if set(frame.market.unique())!=set(symbols):
        raise DownloadError("NOT_ALL_SYMBOLS_RETURNED")
    frame["volume"]=pd.to_numeric(frame.volume,errors="coerce")
    for k in ("open","high","low","close"):
        frame[k]=pd.to_numeric(frame[k],errors="coerce")
    p=frame[["open","high","low","close"]]
    if (not np.isfinite(p.to_numpy()).all() or (p<=0).any().any() or
            (frame.high<p.max(axis=1)).any() or
            (frame.low>frame[["open","high","close"]].min(axis=1)).any()):
        raise DownloadError("SIP_OHLC_QA_FAILED")
    if (frame.volume.isna().any() or (frame.volume<0).any() or
            frame.duplicated(["market","candle_time_utc"]).any()):
        raise DownloadError("SIP_BAD_VOLUME_OR_DUPLICATE")
    frame=frame.sort_values(["market","candle_time_utc"]).reset_index(drop=True)
    return frame,{"request_months":months,"request_pages":pages,
                  "total_bars":len(frame),"symbols":list(symbols),
                  "adjustment":"all","feed":"sip","timeframe":"15Min"}


def summarize(bars, source, start, end, lookback=20):
    """Keep public output to derived statistics and coverage only."""
    features,qa=symbol_volume_features(bars,lookback=lookback)
    periods=[2024,2025,2026]
    output={}
    for symbol,d in features.groupby("symbol"):
        years={}
        for year in periods:
            f=d.loc[d.date_ny.dt.year.eq(year)]
            r=f.rvol20.dropna()
            v=f.rth_volume_shares.dropna()
            years[str(year)]={
                "sessions_expected":int(len(f)),
                "complete_rth_sessions":int(f.complete_rth.sum()),
                "missing_or_partial_rth_sessions":int((~f.complete_rth).sum()),
                "daily_volume_median_shares":round(float(v.median()),2) if len(v) else None,
                "daily_volume_mean_shares":round(float(v.mean()),2) if len(v) else None,
                "rvol20_observations":len(r),
                "rvol20_median":round(float(r.median()),6) if len(r) else None,
                "rvol20_p90":round(float(r.quantile(.9)),6) if len(r) else None,
                "rvol20_p99":round(float(r.quantile(.99)),6) if len(r) else None,
                "rvol20_over_2_fraction":round(float(r.ge(2).mean()),6) if len(r) else None
            }
        subset=bars.loc[bars.market.eq(symbol)]
        n=pd.to_numeric(subset.trade_count,errors="coerce")
        vw=pd.to_numeric(subset.vwap,errors="coerce")
        output[symbol]={
            "years":years,
            "bar_trade_count_present":int(n.notna().sum()),
            "bar_trade_count_missing":int(n.isna().sum()),
            "bar_vwap_present":int(vw.notna().sum()),
            "bar_vwap_missing":int(vw.isna().sum()),
            "bars_raw_not_released":True,
            "model_or_live_ready":False
        }
    complete_ok=all(
        output[s]["years"][str(y)]["missing_or_partial_rth_sessions"]==0
        for s in output for y in (2025,2026))
    return {
        "schema":"kalman-us-five-symbol-15m-volume-source-qa-v1",
        "status":"SOURCE_COVERAGE_GO_MODEL_HOLD" if complete_ok else "HOLD_PARTIAL_SESSIONS",
        "from_utc":start,"to_exclusive_utc":end,"source":source,
        "volume_definition":"ALPACA_SIP_ADJUSTMENT_ALL_15MIN_SHARES_SUM",
        "feature_definition":"RTH RVOL20 vs previous 20 exchange sessions; missing blocks rolling window",
        "source_is_ephemeral":True,
        "do_not_redistribute_licensed_sip":True,
        "trades_and_quotes_not_downloaded_in_this_job":True,
        "data_qa":qa,
        "by_symbol":output,
        "hold_live":True,
        "limitations":[
            "2025 full calendar year vs partial 2026; month-matched stratification required.",
            "Adjusted bars and raw trade notionals require split-safe separate handling.",
            "A data access PASS is not predictive model validation.",
            "SIP provider condition/print eligibility and corrected print chains are not validated here.",
            "No market impact or financing costs in this data coverage report."
        ]
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbols",default="SPY,IWM,SMH,MU,COIN")
    ap.add_argument("--start",default="2024-01-01")
    ap.add_argument("--end-exclusive",default="2026-10-31")
    ap.add_argument("--max-pages-per-month",type=int,default=25)
    ap.add_argument("--out",help="Required except when --self-test is used")
    ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test:
        assert "SPY" in approved_us_symbols()
        print("US_MULTISYMBOL_BACKFILL_SELFTEST_OK")
        return
    if not a.out:
        raise SystemExit("OUTPUT_DIRECTORY_REQUIRED")
    start,end=pd.Timestamp(a.start),pd.Timestamp(a.end_exclusive)
    if start>=end or (end-start).days>1100 or a.max_pages_per_month>30 or a.max_pages_per_month<1:
        raise SystemExit("BACKFILL_RANGE_OR_PAGE_BUDGET_INVALID")
    syms=select_symbols(a.symbols,approved_us_symbols(),max_symbols=5)
    folder=Path(a.out)
    folder.mkdir(parents=True,exist_ok=True)
    key=os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
    secret=os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("ALPACA_SIP_CI_SECRETS_MISSING")
    with requests.Session() as sess:
        try:
            bars,info=get_months(sess,syms,start,end,key,secret,
                                 max_pages_per_month=a.max_pages_per_month)
            report=summarize(bars,info,a.start,a.end_exclusive)
        except (DownloadError,ValueError) as exc:
            (folder/"source_qa.json").write_text(json.dumps(
                {"status":"HOLD","reason":str(exc),"symbols":syms,"hold_live":True},indent=2))
            raise SystemExit("SOURCE_HOLD_"+str(exc)) from None
    # The raw licensed tape must remain only on this ephemeral job.
    bars.to_parquet(folder/"private_15m_bars.parquet",index=False)
    (folder/"source_qa.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print("US_MULTISYMBOL_COVERAGE "+json.dumps(report,ensure_ascii=False),flush=True)
    if report["status"]!="SOURCE_COVERAGE_GO_MODEL_HOLD":
        raise SystemExit(2)


if __name__=="__main__":
    main()
