"""V4.17 continuous-month PAPER grid validation and execution-cost stress.

No exchange calls or credentials. Reanchor on prior close, preserve lots/sells.
Extra costs are sensitivity haircuts, NOT an execution/partial-fill simulation.
"""
import argparse,csv,json
from calendar import monthrange
from pathlib import Path
from decimal import Decimal
from upbit_data_audit_v28 import audit
from upbit_v45_depth_sweep import DepthGrid
D=Decimal

def load(root,months,market):
 rows=[]; boundaries=[]
 for month in months:
  y,m=map(int,month.split("-"))
  path=Path(root)/month/(market+"_1m_history.csv")
  qc=audit(path,1,month+"-01T00:00:00+00:00",f"{month}-{monthrange(y,m)[1]:02d}T23:59:00+00:00")
  if qc["status"]!="PASS":raise RuntimeError("QUALITY_BLOCKED "+month+" "+str(qc))
  with path.open(newline="") as f:
   block=[(r["t"],r["c"]) for r in csv.DictReader(f)]
  if not block or (rows and not rows[-1][0]<block[0][0]):raise RuntimeError("INVALID_MONTH_ORDER")
  rows.extend(block);boundaries.append((month,len(rows)-1))
 return rows,boundaries

def simulate(rows,boundaries,gap,policy,threshold,cooldown,depth,cash,notional,fee,extra_bps):
 g=DepthGrid(rows[0][1],depth=depth,spacing=gap,cash=cash,notional=notional,fee=fee,exposure_cap=cash)
 if len(g.buys)!=depth:raise RuntimeError("INITIAL_BUYS_NOT_FUNDED")
 last_shift=-cooldown;shifts=0;endpoints=[];mark_indices={idx:m for m,idx in boundaries}
 for i in range(1,len(rows)):
  prev=D(rows[i-1][1])
  if policy!="fixed" and i-last_shift>=cooldown:
   delta=(prev/g.anchor-D(1))*100
   if (policy=="upward_only" and delta>=D(threshold)) or (policy=="bidirectional" and abs(delta)>=D(threshold)):
    g.recenter(prev);shifts+=1;last_shift=i
  ts,px=rows[i];g.update(px,ts)
  if i in mark_indices:
   s=g.summary(px)
   endpoints.append({"month":mark_indices[i],"equity":str(s["equity"]),"asset":str(s["asset"]),"open_lots":len(g.ledger.lots),"fills":len(g.fills)})
 g.ledger.audit();s=g.summary(rows[-1][1])
 # Conservative approximate per-side execution friction in basis points,
 # priced at the paper fill price. This is a post-hoc P&L stress, not ledger fills.
 notionals=sum((D(f["price"])*D(f["qty"]) for f in g.fills),D(0))
 return {"gap_pct":gap,"policy":policy,"threshold_pct":threshold,"cooldown_bars":cooldown,
  "depth":depth,"reanchors":shifts,"fills":len(g.fills),
  "buy_fills":sum(f["side"]=="BUY" for f in g.fills),
  "sell_fills":sum(f["side"]=="SELL" for f in g.fills),
  "open_lots":len(g.ledger.lots),"end_equity":str(s["equity"]),
  "return_pct":str(s["return_pct"]),"mdd_pct":str(s["mdd_pct"]),
  "fee_paid":str(s["fees"]),"extra_cost_bps_per_side":str(extra_bps),
  "extra_cost_estimate":str(notionals*D(extra_bps)/D(10000)),
  "stressed_return_pct":str((D(s["equity"])-notionals*D(extra_bps)/D(10000)-D(cash))/D(cash)*100),
  "month_end_states":endpoints}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True);p.add_argument("--out",required=True)
 p.add_argument("--months",default="2026-08,2026-09");p.add_argument("--market",default="KRW-ETH")
 p.add_argument("--gaps",default="0.18,0.21");p.add_argument("--policies",default="fixed,upward_only")
 p.add_argument("--thresholds",default="0.5,1.0")
 p.add_argument("--extra-bps",default="0,1,3,5")
 p.add_argument("--cooldown-bars",type=int,default=240);p.add_argument("--depth",type=int,default=30)
 p.add_argument("--cash",default="1000000");p.add_argument("--notional",default="5500");p.add_argument("--fee",default="0.05")
 a=p.parse_args()
 if a.cooldown_bars<1 or a.depth<1 or D(a.cash)<=0 or D(a.notional)<=0:raise SystemExit("INVALID_CONFIG")
 months=a.months.split(",")
 if months!=sorted(set(months)):raise SystemExit("MONTHS_MUST_BE_SORTED_UNIQUE")
 rows,bounds=load(a.data_root,months,a.market)
 results=[]
 for gap in a.gaps.split(","):
  for policy in a.policies.split(","):
   if policy not in ("fixed","upward_only","bidirectional"):raise SystemExit("UNKNOWN_POLICY")
   for threshold in (["0"] if policy=="fixed" else a.thresholds.split(",")):
    for bps in a.extra_bps.split(","):
     if D(bps)<0:raise SystemExit("NEGATIVE_EXTRA_BPS")
     # The same base path is rerun to make each row auditable, not production code.
     r=simulate(rows,bounds,gap,policy,threshold,a.cooldown_bars,a.depth,a.cash,a.notional,a.fee,bps)
     results.append(r)
     print(json.dumps({k:v for k,v in r.items() if k!="month_end_states"}),flush=True)
 report={"status":"PAPER_RESEARCH_COMPLETE","market":a.market,"months":months,"bars":len(rows),
  "continuous_equity":True,"results":results,
  "caveats":["Close-only fill proxy, no real execution proof","Bps stress is retrospective P&L haircut; not fill-level modeling","Stressed MDD is NOT computed","Historical in-sample, no future performance claim"]}
 dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({"status":report["status"],"scenarios":len(results),"out":str(dest)}))
if __name__=="__main__":main()
