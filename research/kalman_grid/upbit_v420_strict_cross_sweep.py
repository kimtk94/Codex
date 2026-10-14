"""V4.20 strict-through vs touch close-observation PAPER sweep.

Crossing filter requires price beyond limit by N ticks at a 1-minute close.
It is a conservative proxy, NOT an empirical fill-probability estimate.
Preserves standard grid ledger, exposure, inventory, and next-bar orders.
"""
import argparse,csv,json
from pathlib import Path
from decimal import Decimal
from upbit_v417_continuous_cost_stress import load
from upbit_v45_depth_sweep import DepthGrid
from upbit_krw_rules_v33 import snap_price
from kalman_grid_v23 import D

class StrictDepthGrid(DepthGrid):
 def __init__(self,*args,penetration_ticks=0,**kwargs):
  self.penetration_ticks=int(penetration_ticks)
  super().__init__(*args,**kwargs)
 def update(self,price,timestamp=""):
  mark=D(price)
  if mark<=0:raise ValueError("INVALID_MARK")
  # Fixed 1000 KRW increment valid for studied ETH price band only.
  required=D(1000)*self.penetration_ticks
  buys=list(self.buys.items());sells=list(self.sells.items())
  for level,oid in buys:
   order=self.ledger.orders[oid]
   if mark<=order.price-required:
    qty=order.remaining;target=self.limit(level+1,"SELL")
    if target<=order.price:continue
    self.ledger.fill(oid,qty);del self.buys[level]
    lot=next(x for x in self.ledger.lots if x.startswith(oid+":"))
    sid=self.ledger.place("SELL",target,qty,parent_id=oid)
    self.sells[sid]={"level":level,"lot_id":lot}
    self.fills.append({"time":timestamp,"side":"BUY","price":str(order.price),"qty":str(qty),"order_id":oid})
  for sid,info in sells:
   order=self.ledger.orders[sid]
   if mark>=order.price+required:
    qty=order.remaining
    self.ledger.fill(sid,qty,lot_id=info["lot_id"]);del self.sells[sid]
    self.fills.append({"time":timestamp,"side":"SELL","price":str(order.price),"qty":str(qty),"order_id":sid})
  self._fund();self.ledger.audit_fast()
  equity=self.ledger.cash+self.ledger.asset*mark
  self.high=max(self.high,equity)
  self.mdd=max(self.mdd,(self.high-equity)/self.high)

def test(rows,gap,penetration,policy,threshold,cooldown,cash,notional,fee,depth):
 g=StrictDepthGrid(rows[0][1],depth=depth,spacing=gap,cash=cash,notional=notional,
                   fee=fee,exposure_cap=cash,penetration_ticks=penetration)
 if len(g.buys)!=depth:raise ValueError("DEPTH_NOT_FUNDED")
 reanchors=0;last_anchor=-cooldown
 for i in range(1,len(rows)):
  prior=D(rows[i-1][1])
  if policy=="upward_only" and i-last_anchor>=cooldown and (prior/g.anchor-1)*100>=D(threshold):
   g.recenter(prior);reanchors+=1;last_anchor=i
  t,p=rows[i];g.update(p,t)
 g.ledger.audit()
 s=g.summary(rows[-1][1])
 return {"gap_pct":gap,"penetration_ticks":penetration,"policy":policy,"reanchors":reanchors,
         "return_pct":str(s["return_pct"]),"mdd_pct":str(s["mdd_pct"]),
         "fills":len(g.fills),"buy_fills":sum(f["side"]=="BUY" for f in g.fills),
         "sell_fills":sum(f["side"]=="SELL" for f in g.fills),
         "open_lots":len(g.ledger.lots),"fees":str(s["fees"])}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True);p.add_argument("--out",required=True)
 p.add_argument("--months",default="2026-08,2026-09")
 p.add_argument("--gaps",default="0.18,0.21")
 p.add_argument("--penetrations",default="0,1,2")
 p.add_argument("--policies",default="fixed,upward_only")
 p.add_argument("--threshold",default="0.5")
 p.add_argument("--cooldown-bars",type=int,default=240)
 p.add_argument("--depth",type=int,default=30)
 p.add_argument("--cash",default="1000000");p.add_argument("--notional",default="5500")
 p.add_argument("--fee",default="0.08")
 a=p.parse_args()
 if a.cooldown_bars<1 or a.depth<1:raise ValueError("INVALID_CONFIG")
 rows,bounds=load(a.data_root,a.months.split(","),"KRW-ETH")
 # Guard studied price range: fixed tick only supported under this contract.
 if not all(D("2000000")<=D(px)<D("5000000") for _,px in rows):
  raise ValueError("PRICE_BAND_UNSUPPORTED_CHECK_TICK_POLICY")
 result=[]
 for gap in a.gaps.split(","):
  for policy in a.policies.split(","):
   if policy not in ("fixed","upward_only"):raise ValueError("UNKNOWN_POLICY")
   for ticks in map(int,a.penetrations.split(",")):
    if ticks<0:raise ValueError("INVALID_TICKS")
    r=test(rows,gap,ticks,policy,a.threshold,a.cooldown_bars,a.cash,a.notional,a.fee,a.depth)
    result.append(r);print(json.dumps(r),flush=True)
 output={"status":"PAPER_STRICT_CROSS_SWEEP","bars":len(rows),"months":a.months,
         "results":result,
         "limitations":["Minute close beyond limit is a strict threshold proxy, not a limit-order fill simulator.","No queue position, volume allocation, market impact, intrabar path, FX or exchange execution.","The 1000 KRW threshold is limited to checked ETH price band.","No inference about yearly 10% target from two months."]}
 path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(output,ensure_ascii=False,indent=2))
 print(json.dumps({"status":output["status"],"scenarios":len(result),"out":str(path)}))
if __name__=="__main__":main()
