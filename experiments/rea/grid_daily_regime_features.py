#!/usr/bin/env python3
"""Causal daily regime features from ETH 1-minute OHLC; research only."""
import argparse, csv, datetime as dt, json, sqlite3
from collections import defaultdict
from pathlib import Path

KST=dt.timezone(dt.timedelta(hours=9))

def closed_daily_features(candles, short=20, long=60):
    """Regime for local day D uses completed day D-1 and earlier only."""
    last_close={}
    for stamp,close in candles:
        day=dt.datetime.fromisoformat(stamp).astimezone(KST).date()
        last_close[day]=float(close)
    days=sorted(last_close)
    out={}
    for i,day in enumerate(days):
        history=[last_close[d] for d in days[:i]]
        if len(history)<long:
            out[day]={"regime":"WARMUP","source_through":str(days[i-1]) if i else None}
            continue
        fast=sum(history[-short:])/short
        slow=sum(history[-long:])/long
        out[day]={"regime":"UP" if fast>slow else "DOWN","fast":round(fast,6),"slow":round(slow,6),"source_through":str(days[i-1])}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True);p.add_argument("--out",required=True)
    p.add_argument("--start",default="2024-01-01");p.add_argument("--end",default="2026-10-15")
    args=p.parse_args()
    db=Path(args.db).expanduser().resolve()
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
    con.execute("PRAGMA query_only=ON")
    candles=con.execute("SELECT ts_utc,close FROM candles WHERE ts_utc >= ? AND ts_utc < ? ORDER BY ts_utc",(str(dt.datetime.fromisoformat(args.start).replace(tzinfo=KST).astimezone(dt.timezone.utc).isoformat()),str(dt.datetime.fromisoformat(args.end).replace(tzinfo=KST).astimezone(dt.timezone.utc).isoformat()))).fetchall()
    con.close()
    features=closed_daily_features(candles)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["date","regime","fast","slow","source_through"]);w.writeheader()
        for day,row in features.items():w.writerow({"date":str(day),**row})
    counts=defaultdict(int)
    for row in features.values():counts[row["regime"]]+=1
    print(json.dumps({"days":len(features),"counts":dict(counts),"output":str(out),"research_only":True}))
if __name__=="__main__":main()
