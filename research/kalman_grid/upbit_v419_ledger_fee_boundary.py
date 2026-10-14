"""V4.19 funded PAPER fee sensitivity and fixed-anchor reach audit.

Extra bps are modeled as an additional per-side fee INSIDE the ledger,
so they alter reserved cash, order funding, fill cash flows and equity/MDD.
This is NOT a market slippage or limit-order fill-probability model.
"""
import argparse,csv,json
from pathlib import Path
from decimal import Decimal
from upbit_v417_continuous_cost_stress import load
from upbit_v45_depth_sweep import DepthGrid
D=Decimal

def run(rows,bounds,gap,policy,threshold,cooldown,depth,cash,notional,base_fee,bps):
 effective_fee=D(base_fee)+D(bps)/100
 if effective_fee<0:raise ValueError("negative effective fee")
 g=DepthGrid(rows[0][1],depth=depth,spacing=gap,cash=cash,notional=notional,
             fee=str(effective_fee),exposure_cap=cash)
 if len(g.buys)!=depth:raise ValueError("insufficient capital to fund depth")
 start_anchor=g.anchor
 boundary={i:m for m,i in bounds};current=rows[0][0][:7]
 month_stats={m:{"min_close":None,"max_close":None,"fills":0,"buys":0,"sells":0,"first_buy_price":None,
  "last_buy_price":None} for m,_ in bounds}
 month_start_states={};month_ends=[]
 last_shift=-cooldown;shifts=0;previous_fills=0
 for i,(ts,px) in enumerate(rows):
  m=ts[:7];p=D(px)
  if m!=current:
   month_start_states[m]={"timestamp":ts,"anchor":str(g.anchor),
    "active_buys":len(g.buys),"active_sells":len(g.sells),
    "open_lots":len(g.ledger.lots),"cash":str(g.ledger.cash),"free":str(g.ledger.free),
    "lowest_active_buy_price":str(min((g.ledger.orders[oid].price for oid in g.buys.values()),default=D(0))),
    "highest_active_buy_price":str(max((g.ledger.orders[oid].price for oid in g.buys.values()),default=D(0)))}
   current=m
  if i>0 and policy!="fixed" and i-last_shift>=cooldown:
   prior=D(rows[i-1][1]);delta=(prior/g.anchor-1)*100
   if (policy=="upward_only" and delta>=D(threshold)) or (policy=="bidirectional" and abs(delta)>=D(threshold)):
    g.recenter(prior);last_shift=i;shifts+=1
  # Preserve V4.17 first-bar contract: initial bar only sets anchor.
  if i>0:g.update(px,ts)
  s=month_stats[m]
  s["min_close"]=str(p if s["min_close"] is None else min(D(s["min_close"]),p))
  s["max_close"]=str(p if s["max_close"] is None else max(D(s["max_close"]),p))
  for f in g.fills[previous_fills:]:
   s["fills"]+=1;s["buys"]+=f["side"]=="BUY";s["sells"]+=f["side"]=="SELL"
  previous_fills=len(g.fills)
  if i in boundary:
   snap=g.summary(px)
   month_ends.append({"month":boundary[i],"return_pct_to_date":str(snap["return_pct"]),
     "equity":str(snap["equity"]),"open_lots":len(g.ledger.lots),
     "active_buys":len(g.buys),"active_sells":len(g.sells),
     "anchor":str(g.anchor),"month_fills":s["fills"]})
 g.ledger.audit()
 final=g.summary(rows[-1][1])
 return {"gap_pct":str(gap),"policy":policy,"threshold_pct":str(threshold),
  "base_fee_pct_side":str(base_fee),"extra_bps_side":str(bps),
  "effective_fee_pct_side":str(effective_fee),
  "status":"PAPER_LEDGER_FEE_REPLAY","return_pct":str(final["return_pct"]),
  "mdd_pct":str(final["mdd_pct"]),"equity":str(final["equity"]),
  "fills":len(g.fills),"fees_paid":str(final["fees"]),
  "reanchors":shifts,"month_stats":month_stats,
  "month_start_states":month_start_states,"month_end_states":month_ends,
  "first_anchor":str(start_anchor)}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True);p.add_argument("--out",required=True)
 p.add_argument("--months",default="2026-08,2026-09")
 p.add_argument("--gaps",default="0.18,0.21");p.add_argument("--policies",default="fixed,upward_only")
 p.add_argument("--threshold",default="0.5");p.add_argument("--extra-bps",default="0,3,5")
 p.add_argument("--cooldown-bars",type=int,default=240);p.add_argument("--depth",type=int,default=30)
 p.add_argument("--cash",default="1000000");p.add_argument("--notional",default="5500");p.add_argument("--fee",default="0.05")
 a=p.parse_args()
 months=a.months.split(",")
 if months!=sorted(set(months)) or a.depth<1 or a.cooldown_bars<1:raise ValueError("bad config")
 if D(a.cash)<=0 or D(a.notional)<=0:raise ValueError("bad cash/notional")
 rows,bounds=load(a.data_root,months,"KRW-ETH")
 results=[]
 for gap in a.gaps.split(","):
  if D(gap)<=0:raise ValueError("invalid gap")
  for policy in a.policies.split(","):
   if policy not in ("fixed","upward_only","bidirectional"):raise ValueError("invalid policy")
   for bps in a.extra_bps.split(","):
    if D(bps)<0:raise ValueError("invalid friction")
    r=run(rows,bounds,gap,policy,"0" if policy=="fixed" else a.threshold,
          a.cooldown_bars,a.depth,a.cash,a.notional,a.fee,bps)
    results.append(r)
    print(json.dumps({k:v for k,v in r.items() if k not in ("month_stats","month_start_states","month_end_states")},ensure_ascii=False),flush=True)
 report={"status":"PAPER_LEDGER_FEE_STRESS_COMPLETE","market":"KRW-ETH",
         "months":months,"bars":len(rows),"results":results,
         "limitations":"Fee equivalent stress is applied in ledger, NOT a fill-level slippage model. Close-only limit fills remain optimistic. Does not model queue position, order latency, tick-level intrabar paths, or USDT conversions."}
 dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({"status":report["status"],"results":len(results),"out":str(dest)}))
if __name__=="__main__":main()
