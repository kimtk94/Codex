"""Validate OpenBB minute rows and aggregate only complete NYSE regular-session buckets."""
import argparse,json
from pathlib import Path
import pandas as pd

FIELDS=("open","high","low","close","volume")

def normalize(raw):
    d=raw.copy()
    d.index=pd.to_datetime(d.index,utc=True,errors="raise")
    d=d.sort_index(kind="stable")
    missing=[c for c in FIELDS if c not in d.columns]
    if missing:raise ValueError("MISSING_FIELDS:"+",".join(missing))
    for c in FIELDS:d[c]=pd.to_numeric(d[c],errors="raise")
    if d[list(FIELDS)].isna().any().any():raise ValueError("NON_NUMERIC_OHLCV")
    if (d[list(FIELDS[:4])]<=0).any().any() or (d.volume<0).any():raise ValueError("BAD_PRICES_OR_VOLUME")
    if (d.high<d[["open","close","low"]].max(axis=1)).any() or (d.low>d[["open","close","high"]].min(axis=1)).any():raise ValueError("BAD_OHLC")
    duplicates=len(d)-d.index.nunique()
    if duplicates:
        # Reject conflicting duplicates across ALL fields, not merely OHLCV.
        for _,group in d.groupby(level=0):
            if len(group)>1 and not group.eq(group.iloc[0]).all(axis=None):
                raise ValueError("CONFLICTING_DUPLICATE_TIMESTAMP")
        d=d[~d.index.duplicated(keep="first")]
    if d.index.has_duplicates:raise ValueError("DUPLICATES_REMAIN")
    return d,{"raw_rows":len(raw),"unique_rows":len(d),"exact_duplicates_removed":duplicates}

def aggregate(d,minutes):
    if minutes not in (15,60):raise ValueError("UNSUPPORTED_WINDOW")
    # Source timestamps are US/Eastern wall-clock when originally returned tz-naive.
    # The normalized data must already be UTC-aware before this operation.
    local=d.tz_convert("America/New_York")
    local=local.between_time("09:30","15:59")
    grouped=[]
    for day,part in local.groupby(local.index.date):
        origin=pd.Timestamp(str(day)+" 09:30",tz="America/New_York")
        bucket=((part.index-origin).total_seconds()//(minutes*60)).astype(int)
        for number,sub in part.groupby(bucket):
            expected=min(minutes,390-number*minutes)
            if expected<=0:continue
            expected_index=pd.date_range(origin+pd.Timedelta(minutes=number*minutes),periods=expected,freq="min")
            if len(sub)!=expected or not sub.index.equals(expected_index):continue
            grouped.append({"timestamp":expected_index[0].tz_convert("UTC").isoformat(),
                            "open":float(sub.open.iloc[0]),"high":float(sub.high.max()),
                            "low":float(sub.low.min()),"close":float(sub.close.iloc[-1]),
                            "volume":float(sub.volume.sum()),"minutes_in_bucket":expected})
    return pd.DataFrame(grouped)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True);p.add_argument("--output",required=True)
    p.add_argument("--symbol",required=True)
    p.add_argument("--source-timezone",default="America/New_York")
    a=p.parse_args()
    source=pd.read_csv(a.input,index_col=0)
    index=pd.to_datetime(source.index,errors="raise")
    if index.tz is None:index=index.tz_localize(a.source_timezone,ambiguous="raise",nonexistent="raise")
    source.index=index
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    try:
        normalized,stats=normalize(source)
        normalized.to_csv(out/(a.symbol+"_1m_clean.csv"))
        intervals={}
        for m in (15,60):
            frame=aggregate(normalized,m)
            frame.to_csv(out/(a.symbol+f"_{m}m.csv"),index=False)
            intervals[f"{m}m_complete_buckets"]=len(frame)
        result={"symbol":a.symbol,"status":"PASS","source_timezone":a.source_timezone,**stats,**intervals,
                "caveat":"Only complete observed regular-session buckets; timestamps require source timezone verification."}
    except Exception as exc:
        result={"symbol":a.symbol,"status":"BLOCKED","reason":str(exc)[:180]}
    (out/(a.symbol+"_quality.json")).write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    if result["status"]!="PASS":raise SystemExit(2)
if __name__=="__main__":main()
