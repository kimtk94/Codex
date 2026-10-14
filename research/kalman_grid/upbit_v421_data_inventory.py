"""V4.21 inventory audit for two Upbit markets. Zero network calls.
Reports interval coverage and gaps without fabricating zero-volume candles.
"""
import argparse,csv,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

def dt(s):
 return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc)
def audit(path):
 p=Path(path)
 if not p.exists():return {"status":"NOT_FOUND","path":str(p)}
 last=None;count=0;dup=0;outorder=0;gap_minutes=0;max_gap=0;first=None;end=None;invalid=0
 with p.open(newline="",encoding="utf-8-sig") as f:
  reader=csv.DictReader(f)
  if not reader.fieldnames or "t" not in reader.fieldnames or "c" not in reader.fieldnames:return {"status":"BAD_SCHEMA","path":str(p)}
  for row in reader:
   count+=1
   try:
    now=dt(row["t"])
    if float(row["c"])<=0:invalid+=1
   except (ValueError,TypeError,KeyError):
    invalid+=1;continue
   if first is None:first=now
   end=now
   if last is not None:
    diff=(now-last).total_seconds()/60
    if diff==0:dup+=1
    elif diff<0:outorder+=1
    elif diff>1:
     missing=int(diff)-1;gap_minutes+=missing;max_gap=max(max_gap,missing)
   last=now
 return {"status":"PASS" if count and not (invalid or dup or outorder) else "QC_FAIL",
  "path":str(p),"rows":count,"first_utc":first.isoformat() if first else None,
  "last_utc":end.isoformat() if end else None,"missing_minutes_internal":gap_minutes,
  "maximum_internal_gap_minutes":max_gap,"duplicate_timestamps":dup,"out_of_order":outorder,"invalid_rows":invalid}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--root",required=True);p.add_argument("--months",default="2026-08,2026-09")
 p.add_argument("--markets",default="KRW-ETH,USDT-ETH");p.add_argument("--out",required=True)
 a=p.parse_args();results=[]
 for m in a.months.split(","):
  for market in a.markets.split(","):
   results.append({"month":m,"market":market,**audit(Path(a.root)/m/(market+"_1m_history.csv"))})
 result={"status":"INVENTORY_AUDIT","results":results,"caveat":"Internal missing minutes may reflect no trades; independently verify before fill-model use."}
 dst=Path(a.out);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(json.dumps(result,indent=2,ensure_ascii=False))
 print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
