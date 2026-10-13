"""Strict continuity audit for Upbit KRW historical candles. PAPER ONLY."""
import argparse,csv,json
from pathlib import Path
from datetime import datetime,timezone
def parse(s):
    dt=datetime.fromisoformat(s.replace("Z","+00:00"))
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
def audit(file,unit,start=None,end=None):
    with Path(file).open(newline="") as fh:raw=list(csv.DictReader(fh))
    if not raw:return {"status":"FAIL","reason":"EMPTY"}
    stamps=[parse(r["t"]) for r in raw]
    sec=unit*60;spans=[(b-a).total_seconds() for a,b in zip(stamps,stamps[1:])]
    valid=all(s>0 for s in spans)
    begin=parse(start) if start else stamps[0]
    finish=parse(end) if end else stamps[-1]
    expected=int((finish-begin).total_seconds()//sec)+1
    in_window=sum(begin<=t<=finish for t in stamps)
    coverage=in_window/expected if expected>0 else 0
    max_gap=max(spans,default=sec)/60
    gaps=sum(s>sec for s in spans)
    ohlc=all(float(r["h"])>=max(float(r[k]) for k in ("o","l","c")) and float(r["l"])<=min(float(r[k]) for k in ("o","h","c")) for r in raw)
    endpoints=(stamps[0]==begin and stamps[-1]==finish)
    in_bounds=(min(stamps)>=begin and max(stamps)<=finish)
    status="PASS" if valid and ohlc and endpoints and in_bounds and coverage>=.99 and max_gap<=5*unit else "BLOCKED_DATA_QUALITY"
    return {"file":str(file),"status":status,"rows":len(raw),"expected":expected,"coverage_pct":round(coverage*100,3),"gaps":gaps,"max_gap_minutes":max_gap,"start":stamps[0].isoformat(),"end":stamps[-1].isoformat(),"note":"Missing candles may legitimately reflect no trades, but long gaps are a research blocker until cross-validated."}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("files",nargs="+");p.add_argument("--unit",type=int,required=True);p.add_argument("--start");p.add_argument("--end");a=p.parse_args()
    results=[audit(f,a.unit,a.start,a.end) for f in a.files]
    print(json.dumps(results,indent=2))
    if any(r["status"]!="PASS" for r in results):raise SystemExit(2)
