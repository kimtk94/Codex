"""V4.23 preflight: discover ETH/KRW historical 1m coverage and plan bounded backfill.
No network calls, writes only an audit JSON. No orders or private credentials.
"""
import argparse,csv,json,math
from datetime import datetime,timezone,timedelta
from pathlib import Path
from calendar import monthrange

def scan(path,start,end):
 if not path.exists():return {"status":"MISSING","rows":0,"coverage_pct":0,"missing_minutes":int((end-start).total_seconds()/60),"bad_rows":0}
 seen=set();bad=0;dupes=0
 with path.open(newline="",encoding="utf-8-sig") as f:
  rd=csv.DictReader(f)
  if not rd.fieldnames or not {"t","c"}.issubset(rd.fieldnames):
   return {"status":"BAD_SCHEMA","rows":0,"bad_rows":0}
  for r in rd:
   try:
    ts=datetime.fromisoformat(r["t"].replace("Z","+00:00"))
    if ts.tzinfo is None:ts=ts.replace(tzinfo=timezone.utc)
    ts=ts.astimezone(timezone.utc)
    if float(r["c"])<=0:raise ValueError("negative price")
    if start<=ts<end:
     if ts in seen:dupes+=1
     seen.add(ts)
   except (ValueError,TypeError,KeyError):bad+=1
 total=int((end-start).total_seconds()/60)
 missing=max(0,total-len(seen))
 return {"status":"QC_FAIL" if bad or dupes else "OBSERVED",
         "rows":len(seen),"expected_minutes":total,
         "coverage_pct":round(100*len(seen)/total,4),
         "unobserved_minutes":missing,"bad_rows":bad,"duplicate_rows":dupes,
         "first":min(seen).isoformat() if seen else None,
         "last":max(seen).isoformat() if seen else None}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True)
 p.add_argument("--months",default="2024-01:2026-09",help="inclusive YYYY-MM:YYYY-MM")
 p.add_argument("--market",default="KRW-ETH")
 p.add_argument("--out",required=True)
 a=p.parse_args()
 if a.market not in ("KRW-ETH","USDT-ETH"):p.error("unsupported market")
 try:
  lo,hi=a.months.split(":")
  sy,sm=map(int,lo.split("-"));ey,em=map(int,hi.split("-"))
  assert (sy,sm)<=(ey,em) and 1<=sm<=12 and 1<=em<=12
 except Exception:p.error("invalid month range")
 if (ey-sy)*12+em-sm>60:p.error("month span exceeds 61 months")
 root=Path(a.data_root);out=[]
 for y in range(sy,ey+1):
  for m in range(1,13):
   if (y,m)<(sy,sm) or (y,m)>(ey,em):continue
   month=f"{y}-{m:02d}"
   start=datetime(y,m,1,tzinfo=timezone.utc)
   end=datetime(y+1,1,1,tzinfo=timezone.utc) if m==12 else datetime(y,m+1,1,tzinfo=timezone.utc)
   path=root/month/f"{a.market}_1m_history.csv"
   info=scan(path,start,end)
   # Ceiling 200 is only a theoretical lower bound. API sparse candles,
   # overlap and retries make actual page counts different.
   out.append({"month":month,"path":str(path),**info,
               "minimum_pages_if_full_month":math.ceil((end-start).total_seconds()/60/200)})
 manifest={"status":"INVENTORY_ONLY","market":a.market,"months":len(out),"observed_months":sum(x["status"]=="OBSERVED" for x in out),
 "missing_months":sum(x["status"]=="MISSING" for x in out),
 "total_present_rows":sum(x.get("rows",0) for x in out),"monthly":out,
 "notes":["Missing 1m candles can be genuine no-trade intervals; do not invent fills.","Pages counts are lower bounds for full contiguous minutes, not a fetch schedule.","Do not merge independently fetched months before checking time order, duplicates and boundary gaps.","Use V4.21 bounded backfill for small pilots; do not launch an unlimited multi-year collection."]}
 dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in manifest.items() if k!="monthly"},ensure_ascii=False,indent=2))
 for x in out:print(f'{x["month"]} {x["status"]:>10} rows={x["rows"]:>7} coverage={x.get("coverage_pct",0):>8}% path={x["path"]}')
if __name__=="__main__":main()
