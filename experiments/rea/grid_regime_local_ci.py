#!/usr/bin/env python3
"""No-SSH local CI regime attribution. Reads SQLite from runner temp only."""
import argparse, datetime as dt, json, sqlite3
from pathlib import Path
from grid_regime_attribution import POLICIES, simulate
UTC=dt.timezone.utc
KST=dt.timezone(dt.timedelta(hours=9))
def main():
    p=argparse.ArgumentParser();p.add_argument("--db",required=True);p.add_argument("--year",type=int,default=2025);p.add_argument("--output",required=True);p.add_argument("--smoke",action="store_true")
    a=p.parse_args();db=Path(a.db).resolve()
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True);con.execute("PRAGMA query_only=ON")
    first,last,count=con.execute("SELECT MIN(ts_utc),MAX(ts_utc),COUNT(*) FROM candles").fetchone()
    if count<2:raise RuntimeError("NO_CANDLES")
    kst_start=dt.datetime(a.year,1,1,tzinfo=KST).astimezone(UTC)
    kst_end=dt.datetime(a.year+1,1,1,tzinfo=KST).astimezone(UTC)
    expected_span=(kst_end-kst_start).total_seconds()/60
    year_rows=con.execute("SELECT COUNT(*) FROM candles WHERE ts_utc>=? AND ts_utc<?",(kst_start.isoformat(),kst_end.isoformat())).fetchone()[0]
    if not a.smoke and year_rows<expected_span*.99:raise RuntimeError(f"YEAR_COVERAGE_LOW {year_rows}/{expected_span}")
    if a.smoke:
        print("SMOKE_DATA_ONLY="+json.dumps({"rows":count,"min_ts":first,"max_ts":last,"year_rows":year_rows}),flush=True)
        con.close();return
    ystart=(kst_start-dt.timedelta(days=90)).isoformat()
    closing={}
    for ts,close in con.execute("SELECT ts_utc,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",(ystart,kst_end.isoformat())):
        closing[dt.datetime.fromisoformat(ts).astimezone(KST).date()]=float(close)
    days=sorted(closing);regimes={}
    for i,d in enumerate(days):
        if i<60:regimes[d]="WARMUP"
        else:
            vals=[closing[x] for x in days[i-60:i]]
            regimes[d]="UP" if sum(vals[-20:])/20>sum(vals)/60 else "DOWN"
    source=Path("research/upbit_eth/grid_event_v3.py").read_text()
    results={"year":a.year,"source":"CI Upbit 1min","rows":count,"year_rows":year_rows,"policies":{}}
    for spacing in (.01,.015):
        arm={}
        for policy in POLICIES:
            result=simulate(source,con,a.year,spacing,100,1_000_000,.001,regimes,KST,policy)
            arm[policy]=result
            print("CI_ATTRIBUTION="+json.dumps({"spacing":spacing,"policy":policy,**result}),flush=True)
        results["policies"][str(spacing)]=arm
    con.close();Path(a.output).write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print("CI_RESEARCH_PASS=true",flush=True)
if __name__=="__main__":main()
