"""Public Yahoo 15m QLD/QQQ coverage audit, NOT an execution or order audit.

Intraday Yahoo history is typically limited to ~60 days: this is a rolling
snapshot collected in CI, and old bars can no longer be reproduced later.
No live broker access, credentials, or trading actions.
"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .fresh_oos import REF_CLOSE

SYMBOLS=("QLD","QQQ")
FIRST="2026-09-15"
THROUGH="2026-11-11"
TARGET="2026-11-10"
NY="America/New_York"

def download(symbol):
    start=int(pd.Timestamp(FIRST,tz="UTC").timestamp())
    end=int(pd.Timestamp(THROUGH,tz="UTC").timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?"+urllib.parse.urlencode({
        "period1":start,"period2":end,"interval":"15m",
        "includePrePost":"false","events":"history"})
    request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(request,timeout=30) as resp:
        raw=resp.read(5_000_000)
    j=json.loads(raw)["chart"]["result"][0]
    stamps=pd.to_datetime(j["timestamp"],unit="s",utc=True).tz_convert(NY)
    q=j["indicators"]["quote"][0]
    frame=pd.DataFrame({"ts_utc":stamps.tz_convert("UTC").astype(str),
         "date_ny":stamps.date.astype(str),
         "local_time":stamps.strftime("%H:%M"),
         "open":q["open"],"high":q["high"],"low":q["low"],
         "close":q["close"],"volume":q["volume"]})
    return frame,hashlib.sha256(raw).hexdigest()

def coverage(df,symbol,daily):
    required={"ts_utc","date_ny","local_time","open","high","low","close","volume"}
    if required-set(df):raise ValueError("missing intraday columns")
    d=df.copy()
    d["ts_utc"]=pd.to_datetime(d.ts_utc,utc=True,errors="raise")
    if d.ts_utc.isna().any() or d.ts_utc.duplicated().any():
        raise ValueError("duplicate or missing timestamps")
    for k in ("open","high","low","close","volume"):
        d[k]=pd.to_numeric(d[k],errors="coerce")
    d=d.dropna(subset=["open","high","low","close"])
    if d.empty or (d[["open","high","low","close"]]<=0).any().any():
        raise ValueError("empty, nonpositive or null OHLC")
    if ((d.high<d[["open","close","low"]].max(axis=1))|
        (d.low>d[["open","close","high"]].min(axis=1))).any():
        raise ValueError("invalid OHLC")
    clock=pd.to_datetime(d.ts_utc,utc=True).dt.tz_convert(NY)
    minute=clock.dt.hour*60+clock.dt.minute
    rth=d[(minute>=570)&(minute<960)].copy()
    rth=rth.sort_values("ts_utc")
    if rth.empty:raise ValueError("no regular session bars")
    rth["local_time"]=rth.ts_utc.dt.tz_convert(NY).dt.strftime("%H:%M")
    rth["date_ny"]=rth.ts_utc.dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    rows=[]
    for day,g in rth.groupby("date_ny"):
        seen=g.local_time.tolist()
        wanted=pd.date_range("2026-01-01 09:30",periods=26,freq="15min").strftime("%H:%M").tolist()
        contiguous=seen==wanted
        # Do not declare a day complete from row count alone.
        daily_bar=daily.loc[daily.date_ny==day]
        open_delta=None
        if len(daily_bar)==1 and "09:30" in seen:
            first=float(g.loc[g.local_time=="09:30","open"].iloc[0])
            baseline=float(daily_bar[f"open_{symbol.lower()}"].iloc[0])
            open_delta=first/baseline-1
        rows.append({"date_ny":day,"rth_bars":len(g),"has_0930":"09:30" in seen,
                     "full_26_regular_bars":contiguous,
                     "first_bar_open_vs_daily":open_delta})
    summary=pd.DataFrame(rows)
    full=int(summary.full_26_regular_bars.sum())
    start_day=str(summary.date_ny.min())
    last_day=str(summary.date_ny.max())
    opens=summary.first_bar_open_vs_daily.dropna()
    result={
        "symbol":symbol,"status":"PRICE_ONLY_NOT_EXECUTABLE",
        "bars":len(rth),"sessions":len(summary),
        "full_26bar_sessions":full,"incomplete_sessions":len(summary)-full,
        "full_day_fraction":full/len(summary),
        "first_day":start_day,"last_day":last_day,
        "last_complete_close_available":last_day>=TARGET,
        "first_15m_open_match_count":len(opens),
        "max_abs_first_open_vs_daily_pct":float(opens.abs().max()*100) if len(opens) else None,
        "price_source":"Yahoo Finance 15m chart, rolling limited history",
        "actual_broker_fills_attested":False,"promotion_allowed":False}
    return rth,summary,result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--daily",default="results/regime_countertrend/fresh_oos/paired_public_daily_prices.csv")
    p.add_argument("--out",default="results/regime_countertrend/fresh_15m")
    a=p.parse_args()
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    report={"research_only":True,"requested_first":FIRST,"requested_through":THROUGH,
            "recorded_utc":datetime.now(timezone.utc).isoformat(),
            "mode":"PRICE_COVERAGE_NOT_TRADING","symbols":[],"promotion_allowed":False}
    if not Path(a.daily).is_file():
        report["status"]="HOLD_NO_VERIFIED_FRESH_DAILY_BARS"
    else:
        daily=pd.read_csv(a.daily)
        for symbol in SYMBOLS:
            try:
                d,digest=download(symbol)
                bars,days,res=coverage(d,symbol,daily)
                res["raw_sha256"]=digest
                res["last_bar_ts_utc"]=str(bars.ts_utc.max())
                bars.to_csv(root/f"{symbol}_15m_rth.csv",index=False)
                days.to_csv(root/f"{symbol}_sessions.csv",index=False)
            except Exception as exc:
                res={"symbol":symbol,"status":"HOLD_INTRADAY_SOURCE_OR_QC",
                     "error":type(exc).__name__,"detail":str(exc)[:250]}
            report["symbols"].append(res)
        report["status"]="PRICE_BARS_AVAILABLE_NOT_FILLS" if all(
            x["status"]=="PRICE_ONLY_NOT_EXECUTABLE" for x in report["symbols"]) else "HOLD_INCOMPLETE_15M"
    (root/"provenance.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print("FRESH_INTRADAY",json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
