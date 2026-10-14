"""V4.21 bounded, resumable Upbit PUBLIC minute candle backfill.
No keys/orders. Pilot explicitly caps pages to avoid accidental multi-year pulls.
"""
import argparse,csv,json,time,urllib.request,urllib.parse,urllib.error
from pathlib import Path
from datetime import datetime,timezone,timedelta

FIELDS=["t","o","h","l","c","v"]
def utc(s):
 d=datetime.fromisoformat(s.replace("Z","+00:00"))
 if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
 return d.astimezone(timezone.utc)
def fetch(market,cursor):
 params=urllib.parse.urlencode({"market":market,"to":cursor.isoformat().replace("+00:00","Z"),"count":200})
 url="https://api.upbit.com/v1/candles/minutes/1?"+params
 for attempt in range(5):
  try:
   req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"KalmanGridResearch/4.21"})
   with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)
  except urllib.error.HTTPError as e:
   if e.code not in (429,500,502,503,504):raise
   time.sleep(min(20,2**attempt))
  except (TimeoutError,urllib.error.URLError):
   time.sleep(min(20,2**attempt))
 raise RuntimeError("RETRY_EXHAUSTED")
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--market",choices=["KRW-ETH","USDT-ETH"],required=True)
 p.add_argument("--start",required=True,help="inclusive UTC ISO");p.add_argument("--end",required=True,help="exclusive UTC ISO")
 p.add_argument("--out",required=True);p.add_argument("--max-pages",type=int,default=10)
 p.add_argument("--sleep",type=float,default=0.2)
 a=p.parse_args()
 if a.max_pages<1 or a.max_pages>100 or a.sleep<0.11:raise ValueError("BOUNDED_PAGES_OR_RATE_INVALID")
 start=utc(a.start);end=utc(a.end)
 if not start<end<=datetime.now(timezone.utc):raise ValueError("DATE_RANGE_INVALID")
 path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
 existing={}
 if path.exists():
  with path.open(newline="") as f:
   for r in csv.DictReader(f):existing[r["t"]]=r
 cursor=min(end, min((utc(t) for t in existing),default=end))
 total_new=0;pages=0;oldest=cursor
 while pages<a.max_pages and cursor>start:
  candles=fetch(a.market,cursor);pages+=1
  if not candles:break
  seen=[]
  for c in candles:
   d=utc(c["candle_date_time_utc"])
   seen.append(d)
   if start<=d<end:
    t=d.isoformat().replace("+00:00","Z")
    if t not in existing:
     existing[t]={"t":t,"o":c["opening_price"],"h":c["high_price"],
      "l":c["low_price"],"c":c["trade_price"],"v":c["candle_acc_trade_volume"]}
     total_new+=1
  if not seen:break
  next_cursor=min(seen)
  if next_cursor>=cursor:raise RuntimeError("CURSOR_NOT_ADVANCING")
  cursor=next_cursor;oldest=cursor
  if cursor>start:time.sleep(a.sleep)
 tmp=path.with_suffix(path.suffix+".tmp")
 with tmp.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
  for t in sorted(existing):w.writerow(existing[t])
 tmp.replace(path)
 status="RANGE_REACHED" if cursor<=start else "PARTIAL_MORE_PAGES_REQUIRED"
 print(json.dumps({"status":status,"market":a.market,"rows_total":len(existing),"new_rows":total_new,
 "pages":pages,"oldest_cursor":oldest.isoformat(),"output":str(path),
 "warning":"Sparse candles are legitimate; this is a bounded PUBLIC-only collection, not complete coverage proof."},ensure_ascii=False))
if __name__=="__main__":main()
