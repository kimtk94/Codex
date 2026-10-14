"""V4.12 offline diagnostics for zero quote-cross events. Public quotes only."""
import argparse,csv,json
from collections import defaultdict
from decimal import Decimal,ROUND_FLOOR
from pathlib import Path
D=Decimal
def snap(x,tick):return (x/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
def analyze(rows,gaps,tick):
 out=[]
 for market,rr in sorted(rows.items()):
  first=D(rr[0]["ask_krw"])
  asks=[D(x["ask_krw"]) for x in rr]
  bids=[D(x["bid_krw"]) for x in rr]
  last=D(rr[-1]["ask_krw"])
  for gap in gaps:
   entry=snap(first*(1-gap/100),tick)
   crosses=sum(a<=entry for a in asks)
   minimum=min(asks)
   out.append({"market":market,"gap_pct":str(gap),"samples":len(rr),
    "first_ask_krw":str(first),"last_ask_krw":str(last),
    "min_ask_krw":str(minimum),"max_ask_krw":str(max(asks)),
    "min_bid_krw":str(min(bids)),"max_bid_krw":str(max(bids)),
    "first_buy_limit_krw":str(entry),"lowest_ask_minus_first_buy_krw":str(minimum-entry),
    "crossing_snapshot_count":crosses,
    "zero_cross_reason":"PRICE_NEVER_REACHED_FIRST_BUY" if not crosses else "FIRST_LEVEL_TOUCHED",
    "observed_ask_range_pct":float((max(asks)/min(asks)-1)*100)})
 return out
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--csv",required=True)
 p.add_argument("--gaps",default="0.15,0.18,0.21")
 p.add_argument("--tick",default="1000")
 p.add_argument("--out")
 a=p.parse_args()
 rows=defaultdict(list)
 with open(a.csv,newline="") as f:
  for row in csv.DictReader(f):
   if row["market"]=="KRW-ETH":rows[row["market"]].append(row)
 if not rows:raise SystemExit("MISSING_ETH_QUOTES")
 result={"mode":"OFFLINE_DIAGNOSTIC_NO_TRADING","results":analyze(rows,[D(x) for x in a.gaps.split(",")],D(a.tick)),
 "limitations":"Quote snapshots cannot establish an exchange limit fill. Results only describe first-level reach with fixed anchor."}
 val=json.dumps(result,ensure_ascii=False,indent=2)
 print(val)
 if a.out:
  path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(val)
if __name__=="__main__":main()
