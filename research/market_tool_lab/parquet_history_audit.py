"""Read-only quality audit for QQQ hourly parquet already archived on Drive.

Usage: python research/market_tool_lab/parquet_history_audit.py /path/QQQ_1h_2017plus.parquet
Requires pandas+pyarrow; no network or trading APIs. Never publishes raw rows.
"""
import argparse
import json
from pathlib import Path


def audit(path):
    import pandas as pd
    p=Path(path)
    df=pd.read_parquet(p)
    columns={str(c).lower():c for c in df.columns}
    if isinstance(df.index,pd.DatetimeIndex):
        timestamp=df.index
    else:
        key=next((columns[x] for x in ("timestamp","datetime","time","ts","date") if x in columns),None)
        if key is None:
            raise ValueError("no timestamp column or DatetimeIndex")
        timestamp=pd.to_datetime(df[key],errors="coerce",utc=True)
    ts=pd.DatetimeIndex(timestamp)
    if ts.tz is None:
        raise ValueError("ambiguous timezone: DatetimeIndex lacks timezone")
    ts=ts.tz_convert("UTC")
    invalid_time=int(ts.isna().sum())
    duplicated=int(ts.duplicated().sum())
    order_ok=bool(ts.is_monotonic_increasing)
    price_stats={}
    for field in ("open","high","low","close","volume"):
        key=columns.get(field)
        if key is not None:
            vals=pd.to_numeric(df[key],errors="coerce")
            price_stats[field]={"missing":int(vals.isna().sum()),"nonpositive":int((vals<=0).sum()) if field!="volume" else int((vals<0).sum())}
    days=ts.tz_convert("America/New_York").date
    per_day=pd.Series(days).value_counts()
    return {"schema_version":1,"filename":p.name,"rows":len(df),
            "columns":[str(c) for c in df.columns],
            "start_utc":ts.min().isoformat() if len(ts) and not invalid_time else None,
            "end_utc":ts.max().isoformat() if len(ts) and not invalid_time else None,
            "invalid_timestamps":invalid_time,"duplicate_timestamps":duplicated,
            "ordered":order_ok,"sessions_observed":int(len(per_day)),
            "bars_per_session_distribution":{str(k):int(v) for k,v in per_day.value_counts().sort_index().items()},
            "column_quality":price_stats,"note":"Observed bars only; no official market-calendar gap validation, no vendor entitlement or split-adjustment verification."}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("parquet")
    parser.add_argument("--output")
    args=parser.parse_args()
    result=audit(args.parquet)
    payload=json.dumps(result,indent=2,ensure_ascii=False)
    if args.output:Path(args.output).write_text(payload+"\n",encoding="utf-8")
    print(payload)
