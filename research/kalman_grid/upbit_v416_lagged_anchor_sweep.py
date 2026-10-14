"""V4.16 close-only PAPER grid: fixed vs lagged anchor policies.
Never connects to exchanges or touches production. Research comparisons only.
Dynamic recenter uses the previous CLOSED 1m bar, becoming effective at next bar.
Existing inventory and SELL orders remain unchanged.
"""
import argparse,csv,json,os
from pathlib import Path
from calendar import monthrange
from decimal import Decimal
from upbit_data_audit_v28 import audit
from upbit_v45_depth_sweep import DepthGrid
D=Decimal

def run(rows,month,market,gap,policy,threshold_pct,cooldown,depth,cash,notional,fee):
 g=DepthGrid(rows[0][1],depth=depth,spacing=gap,cash=cash,notional=notional,fee=fee,exposure_cap=cash)
 if len(g.buys)!=depth:return {"status":"INSUFFICIENT_INITIAL_FUNDING"}
 last_reanchor=-cooldown
 count=0;shifts=0
 for i in range(1,len(rows)):
  # Prior completed price only. No same-bar decision price for reposition.
  prior=D(rows[i-1][1])
  if policy!="fixed" and i-last_reanchor>=cooldown:
   change=(prior/g.anchor-1)*100
   if ((policy=="bidirectional" and abs(change)>=D(threshold_pct))
       or (policy=="upward_only" and change>=D(threshold_pct))):
    g.recenter(prior)
    shifts+=1;last_reanchor=i
  ts,px=rows[i];g.update(px,ts);count+=1
 g.ledger.audit()
 s=g.summary(rows[-1][1])
 return {"status":"PAPER_CLOSE_ONLY","month":month,"market":market,"gap_pct":gap,
 "policy":policy,"threshold_pct":threshold_pct,"cooldown_bars":cooldown,
 "depth":depth,"reanchors":shifts,"fills":int(s["fills"]),
 "buy_fills":sum(f["side"]=="BUY" for f in g.fills),
 "sell_fills":sum(f["side"]=="SELL" for f in g.fills),
 "return_pct":float(s["return_pct"]),"mdd_pct":float(s["mdd_pct"]),
 "end_equity_krw":float(s["equity"]),"open_lots":len(g.ledger.lots)}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True);p.add_argument("--out-dir",required=True)
 p.add_argument("--months",default="2026-08,2026-09");p.add_argument("--market",default="KRW-ETH")
 p.add_argument("--gaps",default="0.15,0.18,0.21")
 p.add_argument("--policies",default="fixed,upward_only,bidirectional")
 p.add_argument("--thresholds",default="0.5,1.0")
 p.add_argument("--cooldown-bars",type=int,default=240)
 p.add_argument("--depth",type=int,default=30)
 p.add_argument("--cash",default="1000000");p.add_argument("--notional",default="5500");p.add_argument("--fee",default="0.05")
 a=p.parse_args()
 if a.cooldown_bars<1 or a.depth<1:raise SystemExit("INVALID_CONFIG")
 out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
 results=[]
 for month in a.months.split(","):
  y,m=map(int,month.split("-"))
  path=Path(a.data_root)/month/f"{a.market}_1m_history.csv"
  qc=audit(path,1,f"{month}-01T00:00:00+00:00",f"{month}-{monthrange(y,m)[1]:02d}T23:59:00+00:00")
  if qc["status"]!="PASS":raise SystemExit(f"QUALITY_BLOCKED {month}: {qc}")
  with path.open(newline="") as f:rows=[(r["t"],r["c"]) for r in csv.DictReader(f)]
  for gap in a.gaps.split(","):
   for policy in a.policies.split(","):
    for threshold in (["0"] if policy=="fixed" else a.thresholds.split(",")):
     v=run(rows,month,a.market,gap,policy,threshold,a.cooldown_bars,a.depth,a.cash,a.notional,a.fee)
     results.append(v);print(json.dumps(v),flush=True)
 dest=out/"v416_anchor_sweep.csv"
 with dest.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 (out/"v416_contract.json").write_text(json.dumps({"status":"RESEARCH_ONLY","source":"1m close-only per independent month",
  "forward_safe":"recenter determined by previous completed bar; evaluated on next bar",
  "known_limitations":"No intrabar paths, limit order queues, partial fills, adverse selection, or execution slippage. Historical research, not OOS approval. Volatility-adaptive mode intentionally excluded until accounting validated.",
  "live_ordering":False},indent=2))
 print(json.dumps({"status":"COMPLETE","scenarios":len(results),"csv":str(dest)}))
if __name__=="__main__":main()
