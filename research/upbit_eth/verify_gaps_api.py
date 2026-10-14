#!/usr/bin/env python3
"""Verify historical gaps against fresh Upbit KRW-ETH 1-minute API responses; read-only."""
import argparse,datetime as dt,json,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--report",default="results/gap_report.json")
p.add_argument("--limit",type=int,default=30)
p.add_argument("--out",default="results/gap_api_verification.json")
a=p.parse_args()
gaps=json.loads(Path(a.report).read_text())["top_30_gaps"][:a.limit]
result=[]
for i,g in enumerate(gaps,1):
    st=dt.datetime.fromisoformat(g["start_utc"])
    en=dt.datetime.fromisoformat(g["end_utc"])
    probes=[st+dt.timedelta(minutes=1),st+(en-st)/2,en+dt.timedelta(minutes=1)]
    records=[]
    for target in probes:
        cutoff=target+dt.timedelta(minutes=1)
        url="https://api.upbit.com/v1/candles/minutes/1?"+urllib.parse.urlencode({"market":"KRW-ETH","to":cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),"count":2})
        try:
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url,headers={"Accept":"application/json"}),timeout=20) as f: rows=json.load(f)
                    break
                except (urllib.error.URLError,TimeoutError):
                    if attempt==4: raise
                    time.sleep(2**attempt)
            observed=[r["candle_date_time_utc"] for r in rows]
            in_gap=[x for x in observed if st <= dt.datetime.fromisoformat(x).replace(tzinfo=dt.timezone.utc)<=en]
            records.append({"query_target_utc":target.isoformat(),"returned_utc":observed,"inside_original_gap":in_gap})
        except Exception as exc:records.append({"query_target_utc":target.isoformat(),"error":str(exc)})
        time.sleep(.16)
    out=dict(gap=g,probes=records,api_candles_found_inside_gap=any(x.get("inside_original_gap") for x in records))
    result.append(out)
    print(f'{i}/{len(gaps)} gap_minutes={g["minutes"]} found_inside={out["api_candles_found_inside_gap"]}',flush=True)
path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps({"note":"Spot checks only, not exhaustive; a no-match does not prove exchange downtime.","results":result},ensure_ascii=False,indent=2))
print("SAVED",path)
