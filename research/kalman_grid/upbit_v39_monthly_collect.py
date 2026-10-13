"""PAPER ONLY: multi-month Upbit 1m collection launcher, explicitly separate month dirs.

Run collection separately from analysis. No credential/broker calls.
"""
import argparse,calendar,subprocess,sys,json
from pathlib import Path

def months_between(start,end):
 y,m=map(int,start.split("-"));ey,em=map(int,end.split("-"))
 if (y,m)>(ey,em):raise ValueError("bad month range")
 while (y,m)<=(ey,em):
  yield y,m
  m+=1
  if m==13:y,m=y+1,1

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--start-month",required=True,help="YYYY-MM")
 p.add_argument("--end-month",required=True,help="YYYY-MM")
 p.add_argument("--data-root",required=True)
 p.add_argument("--execute",action="store_true",help="Actual public-data read; otherwise only display plan")
 a=p.parse_args();root=Path(a.data_root)
 script=Path(__file__).with_name("upbit_history_v28.py")
 audit=Path(__file__).with_name("upbit_data_audit_v28.py")
 for y,m in months_between(a.start_month,a.end_month):
  if (y,m)>=(2026,10):raise ValueError("Use only finished pre-October months in this launcher")
  ny,nm=(y+1,1) if m==12 else (y,m+1)
  start=f"{y:04d}-{m:02d}-01T00:00:00Z";end=f"{ny:04d}-{nm:02d}-01T00:00:00Z"
  dest=root/f"{y:04d}-{m:02d}"
  days=calendar.monthrange(y,m)[1]
  pages=(days*1440+199)//200+8
  csvs=[str(dest/f"{market}_1m_history.csv") for market in ("KRW-BTC","KRW-ETH")]
  collection=[sys.executable,str(script),"--unit","1","--start",start,"--end",end,"--out-dir",str(dest),"--max-pages",str(pages)]
  last=f"{ny:04d}-{nm:02d}-01T00:00:00Z"
  from datetime import datetime,timedelta,timezone
  last=(datetime.fromisoformat(last.replace("Z","+00:00"))-timedelta(minutes=1)).isoformat()
  check=[sys.executable,str(audit),"--unit","1","--start",start,"--end",last,*csvs]
  print(json.dumps({"month":f"{y:04d}-{m:02d}","collection":collection,"audit":check}),flush=True)
  if a.execute:
   missing=[market for market,csv_path in zip(("KRW-BTC","KRW-ETH"),csvs) if not Path(csv_path).exists()]
   if missing:
    subprocess.run(collection+["--markets",",".join(missing)],check=True)
   else:
    print("EXISTING_INPUT_REAUDIT",dest,flush=True)
   subprocess.run(check,check=True)
if __name__=="__main__":main()
