"""V4.18 month-boundary audit + pathwise cost-adjusted PAPER equity.

No network, credentials, or orders. Friction is a cash-equivalent shadow
deduction on each observed hypothetical fill; it DOES NOT change fills,
funding, queue priority, or market impact. This is not executable P&L.
"""
import argparse,csv,json
from pathlib import Path
from decimal import Decimal
from upbit_v417_continuous_cost_stress import load
from upbit_v45_depth_sweep import DepthGrid
D=Decimal
def run(rows,bounds,gap,policy,threshold,cooldown,depth,cash,notional,fee,bps):
 g=DepthGrid(rows[0][1],depth=depth,spacing=gap,cash=cash,notional=notional,fee=fee,exposure_cap=cash)
 if len(g.buys)!=depth:raise ValueError("UNFUNDED_LEVELS")
 boundary={idx:m for m,idx in bounds}
 prev_month=rows[0][0][:7]
 shifts=0;last_shift=-cooldown;extra=D(0);max_equity=D(cash);mdd=D(0)
 monthly=[];n_seen=0;first_next={};last_fills=0
 for i in range(1,len(rows)):
  ts,px=rows[i];month=ts[:7]
  if month!=prev_month:
   first_next[month]={"first_ts":ts,"pre_bar_active_buy_orders":len(g.buys),
    "pre_bar_active_sell_orders":len(g.sells),"pre_bar_open_lots":len(g.ledger.lots),
    "pre_bar_cash":str(g.ledger.cash),"pre_bar_asset":str(g.ledger.asset)}
   prev_month=month
  prior=D(rows[i-1][1])
  if policy!="fixed" and i-last_shift>=cooldown:
   delta=(prior/g.anchor-1)*100
   if (policy=="upward_only" and delta>=D(threshold)) or (policy=="bidirectional" and abs(delta)>=D(threshold)):
    g.recenter(prior);shifts+=1;last_shift=i
  old=len(g.fills)
  g.update(px,ts)
  for f in g.fills[old:]:
   extra+=D(f["price"])*D(f["qty"])*D(bps)/D(10000)
  eq=g.ledger.cash+g.ledger.asset*D(px)-extra
  max_equity=max(max_equity,eq)
  mdd=max(mdd,(max_equity-eq)/max_equity)
  if i in boundary:
   snap=g.summary(px)
   monthly.append({"month":boundary[i],"month_end_ts":ts,"base_equity":str(snap["equity"]),
    "shadow_cost_adjusted_equity":str(eq),"cumulative_shadow_cost":str(extra),
    "total_fills":len(g.fills),"month_fills":len(g.fills)-last_fills,
    "open_lots":len(g.ledger.lots),"active_buy_orders":len(g.buys),
    "active_sell_orders":len(g.sells),"cash":str(g.ledger.cash),
    "asset":str(g.ledger.asset),"anchor":str(g.anchor),
    "last_close":str(px)})
   last_fills=len(g.fills)
 g.ledger.audit()
 return {"gap_pct":gap,"policy":policy,"threshold_pct":threshold,"extra_bps_each_side":str(bps),
  "fills":len(g.fills),"reanchors":shifts,"base_return_pct":str((g.ledger.cash+g.ledger.asset*D(rows[-1][1])-D(cash))/D(cash)*100),
  "shadow_cost_adjusted_return_pct":str((eq-D(cash))/D(cash)*100),
  "shadow_cost_adjusted_mdd_pct":str(mdd*100),
  "extra_cost_krw":str(extra),"month_end":monthly,"next_month_open":first_next}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True);p.add_argument("--out",required=True)
 p.add_argument("--months",default="2026-08,2026-09")
 p.add_argument("--gaps",default="0.18,0.21")
 p.add_argument("--policies",default="fixed,upward_only")
 p.add_argument("--thresholds",default="0.5")
 p.add_argument("--extra-bps",default="0,3")
 p.add_argument("--cooldown-bars",type=int,default=240);p.add_argument("--depth",type=int,default=30)
 p.add_argument("--cash",default="1000000");p.add_argument("--notional",default="5500");p.add_argument("--fee",default="0.05")
 a=p.parse_args()
 months=a.months.split(",");rows,bounds=load(a.data_root,months,"KRW-ETH")
 results=[]
 for gap in a.gaps.split(","):
  for policy in a.policies.split(","):
   if policy not in ("fixed","upward_only","bidirectional"):raise ValueError("UNKNOWN_POLICY")
   for thresh in (["0"] if policy=="fixed" else a.thresholds.split(",")):
    for bps in a.extra_bps.split(","):
     if D(bps)<0:raise ValueError("NEGATIVE_FRICTION")
     result=run(rows,bounds,gap,policy,thresh,a.cooldown_bars,a.depth,a.cash,a.notional,a.fee,bps)
     results.append(result)
     print(json.dumps({k:v for k,v in result.items() if k not in ("month_end","next_month_open")},ensure_ascii=False),flush=True)
 report={"status":"PAPER_PATHWISE_AUDIT","bars":len(rows),"results":results,
  "limitations":"Shadow cost deducted each hypothetical fill from valuation; no change to ledger funding/orders/fill decisions. MDD is pathwise SHADOW MDD, not executable MDD. Uses close-only hypothetical fills."}
 path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({"status":report["status"],"scenarios":len(results),"file":str(path)}))
if __name__=="__main__":main()
