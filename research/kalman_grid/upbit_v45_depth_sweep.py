"""PAPER ONLY independent funded BUY-depth sweep; no LIVE/broker API."""
import argparse,csv,json,os
from calendar import monthrange
from pathlib import Path
from upbit_data_audit_v28 import audit
from upbit_paper_grid_v35 import UpbitPaperGrid
from kalman_grid_v23 import D

class DepthGrid(UpbitPaperGrid):
 def __init__(self,anchor,*,depth,**kw):
  self.depth=depth
  super().__init__(anchor,levels=2*depth,**kw)
 def _fund(self):
  self.buy_levels=list(range(-1,-self.depth-1,-1))
  return super()._fund()

def one(obs,month,market,gap,depth,cash,notional,fee):
 g=DepthGrid(obs[0][1],depth=depth,spacing=gap,cash=cash,notional=notional,fee=fee,exposure_cap=cash)
 initial=len(g.buys)
 fields=dict(month=month,market=market,gap_pct=gap,depth=depth,initial_funded_buys=initial,
   initial_locked_krw=float(g.ledger.locked),cash_krw=float(D(cash)),order_krw=float(D(notional)))
 if initial!=depth:
  return dict(fields,status="BLOCKED_INSUFFICIENT_CAPITAL",return_pct="",mdd_pct="",fills="",
    buy_fills="",sell_fills="",peak_inventory_krw="",peak_reserved_krw="",peak_exposure_pct="",end_equity_krw="")
 peak_inventory=D(0);peak_reserved=g.ledger.locked;peak_exposure=g.ledger.locked
 for ts,price in obs[1:]:
  g.update(price,ts)
  inv=g.ledger.inventory_cost();reserved=g.ledger.locked
  peak_inventory=max(peak_inventory,inv);peak_reserved=max(peak_reserved,reserved)
  peak_exposure=max(peak_exposure,inv+reserved)
 g.ledger.audit();s=g.summary(obs[-1][1]);b=sum(f["side"]=="BUY" for f in g.fills)
 return dict(fields,status="PAPER_COMPLETE",return_pct=float(s["return_pct"]),mdd_pct=float(s["mdd_pct"]),
   fills=len(g.fills),buy_fills=b,sell_fills=len(g.fills)-b,
   peak_inventory_krw=float(peak_inventory),peak_reserved_krw=float(peak_reserved),
   peak_exposure_pct=float(peak_exposure/D(cash)*100),end_equity_krw=float(s["equity"]))

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True);p.add_argument("--out-dir",required=True)
 p.add_argument("--months",default="2026-08,2026-09")
 p.add_argument("--market",default="KRW-ETH")
 p.add_argument("--spacings",default="0.12,0.15,0.18,0.21,0.25,0.30,0.50")
 p.add_argument("--depths",default="25,50,75,100,125,150,175,181,200,300")
 p.add_argument("--cash",default="1000000");p.add_argument("--notional",default="5500")
 p.add_argument("--fee",default="0.05");p.add_argument("--limit",type=int,default=0)
 a=p.parse_args();root=Path(a.data_root);out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
 results=[];dest=out/"v45_depth_results.csv"
 for month in a.months.split(","):
  y,m=map(int,month.split("-"))
  path=root/month/f"{a.market}_1m_history.csv"
  q=audit(path,1,f"{month}-01T00:00:00+00:00",f"{month}-{monthrange(y,m)[1]:02d}T23:59:00+00:00")
  if q["status"]!="PASS":raise SystemExit(f"QUALITY_BLOCKED {month}: {q}")
  with path.open(newline="") as f: obs=[(r["t"],r["c"]) for r in csv.DictReader(f)]
  for gap in a.spacings.split(","):
   for depth in map(int,a.depths.split(",")):
    if a.limit and len(results)>=a.limit:break
    r=one(obs,month,a.market,gap,depth,a.cash,a.notional,a.fee)
    results.append(r)
    temp=dest.with_suffix(".tmp")
    with temp.open("w",newline="") as f:
     w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    os.replace(temp,dest)
    print(json.dumps({k:r[k] for k in ("month","gap_pct","depth","initial_funded_buys","status","return_pct","mdd_pct","fills")}),flush=True)
   if a.limit and len(results)>=a.limit:break
  if a.limit and len(results)>=a.limit:break
 (out/"v45_manifest.json").write_text(json.dumps({"paper_only":True,"scenarios":len(results),"months":a.months,
 "cash_krw":a.cash,"notional_krw":a.notional,"fee_pct_each_side":a.fee,
 "limitations":"Close-only hypothetical fills; 1m OHLC path, order book, queue and real slippage not modeled.",
 "comparison":"Independent months; rejected 200/300 requested BUY depths if insufficient funded cash"},indent=2))
 print(json.dumps({"status":"COMPLETE","rows":len(results),"csv":str(dest)}))
if __name__=="__main__":main()
