"""Analyze V4.8 public quotes for grid feasibility; never send orders."""
import argparse,csv,json,statistics
from collections import defaultdict
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from datetime import datetime,timezone

D=Decimal

def evaluate(rows,gaps,fee_pct,notional):
  report={"mode":"PAPER_DIAGNOSTIC_ONLY","samples":len(rows),"markets":{}}
  groups=defaultdict(list)
  for r in rows:groups[r["market"]].append(r)
  for market,rr in sorted(groups.items()):
    spreads=[float(r["spread_pct_mid"]) for r in rr]
    delays=[]
    for r in rr:
      t=datetime.fromisoformat(r["observed_at_utc"].replace("Z","+00:00")).timestamp()*1000
      delays.append(max(0,round(t-float(r["book_ts_ms"]))))
    market_result={"count":len(rr),"spread_pct_min":min(spreads),"spread_pct_median":statistics.median(spreads),"spread_pct_p95":sorted(spreads)[min(len(spreads)-1,int(.95*(len(spreads)-1)))],"spread_pct_max":max(spreads),"book_age_ms_median":statistics.median(delays),"book_age_ms_max":max(delays),"grids":[]}
    for gap in gaps:
      valid=0;profits=[];actual_gaps=[];negative=0
      for r in rr:
        bid=D(r["bid_krw"]);ask=D(r["ask_krw"])
        # Conservative taker-like roundtrip proxy: buy at ask, sell at a target
        # gap above ask, with tick alignment. Assumes exit fills at target;
        # not an exchange fill simulator.
        tick=D("1000")
        target=(ask*(D("1")+gap/D("100"))/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        if target<=ask:continue
        qty=notional/ask
        cost=notional*fee_pct/D("100")
        proceeds=qty*target
        sell_fee=proceeds*fee_pct/D("100")
        pnl=proceeds-notional-cost-sell_fee
        profits.append(float(pnl));actual_gaps.append(float((target/ask-1)*100))
        valid+=1
        if pnl<=0:negative+=1
      market_result["grids"].append({"gap_pct":str(gap),"valid_quotes":valid,"positive_net_fraction":(valid-negative)/valid if valid else None,"net_krw_median":statistics.median(profits) if profits else None,"net_krw_min":min(profits) if profits else None,"actual_gap_pct_median":statistics.median(actual_gaps) if actual_gaps else None,"tick_assumption_krw":1000})
    report["markets"][market]=market_result
  return report

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--csv",required=True);p.add_argument("--gaps",default="0.15,0.18,0.21")
 p.add_argument("--fee-pct",default="0.05");p.add_argument("--notional",default="5500")
 a=p.parse_args()
 with open(a.csv,newline="") as f:rows=list(csv.DictReader(f))
 if not rows:raise SystemExit("EMPTY_CSV")
 required={"market","observed_at_utc","bid_krw","ask_krw","spread_pct_mid","book_ts_ms"}
 if not required.issubset(rows[0]):raise SystemExit("MISSING_COLUMNS")
 for r in rows:
  if D(r["bid_krw"])<=0 or D(r["ask_krw"])<D(r["bid_krw"]):raise SystemExit("INVALID_BOOK")
 out=evaluate(rows,[D(x) for x in a.gaps.split(",")],D(a.fee_pct),D(a.notional))
 print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
