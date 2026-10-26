"""Strict read-only minute OHLCV parity against an independently sourced Alpaca CSV.

Both CSV inputs must contain timestamp, open, high, low, close, volume.
Timestamps must include UTC offsets; no local-time guessing, no forward filling.
"""
import argparse,json
from pathlib import Path
import pandas as pd

COLS=["open","high","low","close","volume"]

def load(path):
    d=pd.read_csv(path)
    if "timestamp" not in d.columns: raise ValueError("MISSING_TIMESTAMP")
    stamp=d["timestamp"].astype(str)
    if not stamp.str.contains(r"(?:Z|[+-]\d\d:\d\d)$",regex=True).all():
        raise ValueError("TIMESTAMPS_REQUIRE_EXPLICIT_UTC_OFFSET")
    d["timestamp"]=pd.to_datetime(d["timestamp"],utc=True)
    if d.timestamp.duplicated().any():raise ValueError("DUPLICATE_TIMESTAMP")
    for col in COLS:
        if col not in d: raise ValueError("MISSING_"+col.upper())
        d[col]=pd.to_numeric(d[col],errors="raise")
    if d[COLS].isna().any().any():raise ValueError("NULL_VALUES")
    if (d[COLS[:4]]<=0).any().any() or (d.volume<0).any():raise ValueError("INVALID_PRICE_VOLUME")
    return d.set_index("timestamp").sort_index()

def compare(openbb,alpaca):
    a,b=load(openbb),load(alpaca)
    common=a.index.intersection(b.index)
    report={"openbb_rows":len(a),"alpaca_rows":len(b),"common_minutes":len(common),
            "openbb_only":len(a.index.difference(b.index)),
            "alpaca_only":len(b.index.difference(a.index)),
            "status":"NO_OVERLAP","metrics":{}}
    if not len(common):return report
    x,y=a.loc[common],b.loc[common]
    metrics={}
    for col in COLS[:4]:
        dif=(x[col]-y[col]).abs()
        metrics[col]={"exact_match_count":int((dif<1e-10).sum()),
                      "max_abs_usd":round(float(dif.max()),6),
                      "p95_abs_usd":round(float(dif.quantile(.95)),6)}
    volbase=y.volume.replace(0,float("nan"))
    gap=((x.volume-y.volume).abs()/volbase*100).dropna()
    metrics["volume"]={"max_abs_gap_pct":round(float(gap.max()),5) if len(gap) else None,
                       "median_abs_gap_pct":round(float(gap.median()),5) if len(gap) else None,
                       "alpaca_zero_volume_count":int((y.volume==0).sum())}
    report["metrics"]=metrics
    report["status"]="REVIEW_REQUIRED"
    report["caution"]="Cross-feed OHLCV differences are descriptive; venue coverage, SIP/IEX entitlement, corporate actions, market session, timestamp convention and revisions remain unverified."
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--openbb",required=True);p.add_argument("--alpaca",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    result=compare(a.openbb,a.alpaca)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
