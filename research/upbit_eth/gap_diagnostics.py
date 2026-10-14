#!/usr/bin/env python3
"""Read-only SQLite gap diagnostics; no third-party dependencies."""
import argparse, sqlite3, datetime as dt, collections, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--db",default="krw_eth_1m.sqlite3")
p.add_argument("--out",default="results/gap_report.json")
a=p.parse_args()
con=sqlite3.connect("file:"+str(Path(a.db).resolve())+"?mode=ro",uri=True)
con.execute("PRAGMA query_only=ON")
q=con.execute("SELECT ts_utc FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",("2023-12-31T15:00:00+00:00","2026-10-14T10:00:00+00:00"))
prev=None; gaps=[]; distribution=collections.Counter(); by_year=collections.Counter(); total=0
for (raw,) in q:
    t=dt.datetime.fromisoformat(raw)
    if prev is not None:
        missed=int((t-prev).total_seconds()/60)-1
        if missed>0:
            s=prev+dt.timedelta(minutes=1);e=t-dt.timedelta(minutes=1)
            gaps.append({"start_utc":s.isoformat(),"end_utc":e.isoformat(),"minutes":missed,"start_kst":s.astimezone(dt.timezone(dt.timedelta(hours=9))).isoformat()})
            distribution["1" if missed==1 else "2-5" if missed<=5 else "6-30" if missed<=30 else "31-120" if missed<=120 else "121+"]+=1
            y=s.astimezone(dt.timezone(dt.timedelta(hours=9))).year
            by_year[str(y)]+=missed
            total+=missed
    prev=t
report={"gap_count":len(gaps),"missing_minutes":total,"gap_size_distribution":dict(distribution),"missing_minutes_by_gap_start_year":dict(by_year),"top_30_gaps":sorted(gaps,key=lambda x:x["minutes"],reverse=True)[:30],"sample_single_minute_gaps":[g for g in gaps if g["minutes"]==1][:20]}
path=Path(a.out);path.parent.mkdir(exist_ok=True,parents=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
print("SAVED",path)
