"""Coverage and temporal integrity audit of Drive-frozen 15-minute price bars.

Read-only market data only. This NEVER interprets mirror trades as broker fills.
"""
import argparse
import base64
import io
import json
from pathlib import Path
import pandas as pd

SYMBOLS=("INTC","AMAT","AMD","ORCL","MU")
TS_FIELDS=("datetime","timestamp","ts_utc","ts","date","time","bar_time","index")
OHLC=("open","high","low","close")

def analyze_frame(raw,symbol):
    data=raw.copy()
    if isinstance(data.columns,pd.MultiIndex):
        # Require a single unambiguous OHLC price series.
        data.columns=["_".join(str(x) for x in tup if x is not None).lower() for tup in data.columns]
    else:
        data.columns=[str(c).strip().lower() for c in data.columns]
    if isinstance(data.index,pd.DatetimeIndex) and not any(c in data for c in TS_FIELDS):
        data=data.reset_index()
        data.columns=[str(c).strip().lower() for c in data.columns]
    names=list(data.columns)
    field=next((x for x in TS_FIELDS if x in data.columns),None)
    if field is None:
        return {"symbol":symbol,"status":"HOLD_UNKNOWN_TIMESTAMP_SCHEMA","columns":names}
    t=pd.to_datetime(data[field],utc=True,errors="coerce")
    if t.isna().any() or t.duplicated().any():
        return {"symbol":symbol,"status":"HOLD_INVALID_OR_DUPLICATE_TIMESTAMPS","columns":names}
    if not all(x in data for x in OHLC):
        return {"symbol":symbol,"status":"HOLD_UNKNOWN_OHLC_SCHEMA","columns":names}
    x=data.copy();x["time_utc"]=t
    x=x.sort_values("time_utc")
    for f in OHLC:
        x[f]=pd.to_numeric(x[f],errors="coerce")
    if x[list(OHLC)].isna().any().any() or (x[list(OHLC)]<=0).any().any():
        return {"symbol":symbol,"status":"HOLD_INVALID_OHLC_VALUES","columns":names}
    if ((x.high<x[list(("open","close","low"))].max(axis=1))|
        (x.low>x[list(("open","close","high"))].min(axis=1))).any():
        return {"symbol":symbol,"status":"HOLD_INCONSISTENT_OHLC_RANGE","columns":names}
    diffs=x.time_utc.diff().dropna()
    exact15=int((diffs==pd.Timedelta(minutes=15)).sum())
    local=x.time_utc.dt.tz_convert("America/New_York")
    # Most source providers may include pre-market/after-hours; distinguish RTH.
    clock=local.dt.hour*60+local.dt.minute
    rth=(clock>=570)&(clock<960)&(local.dt.dayofweek<5)
    daily=x.loc[rth].groupby(local.loc[rth].dt.date).size()
    close_days=int((daily>=26).sum())
    usable=int(len(daily))
    return {
      "symbol":symbol,"status":"PRICE_COVERAGE_ONLY_NOT_FILLS","rows":int(len(x)),
      "first_utc":x.time_utc.iloc[0].isoformat(),"last_utc":x.time_utc.iloc[-1].isoformat(),
      "first_ny":local.iloc[0].isoformat(),"last_ny":local.iloc[-1].isoformat(),
      "unique_ny_days":int(local.dt.date.nunique()),
      "rth_days":usable,"rth_full_26bar_days":close_days,
      "rth_full_day_fraction":round(close_days/usable,4) if usable else 0,
      "adjacent_15m_pairs":exact15,
      "adjacent_15m_pair_fraction":round(exact15/len(diffs),4) if len(diffs) else 0,
      "ohlc_source":"UNADJUSTED_OR_UNVERIFIED",
      "columns":names}
def audit_folder(folder):
    root=Path(folder)
    report=[]
    for sym in SYMBOLS:
        fp=root/(sym+"_15m.parquet.b64")
        if not fp.exists():
            report.append({"symbol":sym,"status":"HOLD_MISSING_PRICE_FILE"})
            continue
        try:
            raw=base64.b64decode(fp.read_text().strip(),validate=True)
            frame=pd.read_parquet(io.BytesIO(raw))
            result=analyze_frame(frame,sym)
            result["file_bytes"]=len(raw)
            report.append(result)
        except Exception as exc:
            report.append({"symbol":sym,"status":"HOLD_PARSE_FAILURE","error_type":type(exc).__name__})
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--dir",default="research/regime_countertrend/data/price_15m")
    p.add_argument("--out",default="results/regime_countertrend/price_15m")
    a=p.parse_args()
    report=audit_folder(a.dir)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"coverage.json").write_text(json.dumps({"status":"PRICE_ONLY_NO_BROKER_FILL_MATCH",
     "records":report,"research_only":True},ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))
