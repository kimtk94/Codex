#!/usr/bin/env python3
"""Read-only per-lot Upbit 1m grid research: prior-close signal, next-open execution."""
import argparse,sqlite3,json
from pathlib import Path
import pandas as pd
def run(a):
 c=sqlite3.connect(f"file:{Path(a.db).expanduser()}?mode=ro",uri=True);c.execute("PRAGMA query_only=ON")
 d=pd.read_sql_query("SELECT ts_utc,open,high,low,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",c,params=(a.start,a.end));c.close()
 if len(d)<100:raise ValueError("Not enough candles")
 d["ts"]=pd.to_datetime(d.ts_utc,utc=True);d=d.drop_duplicates("ts").sort_values("ts")
 cash=a.initial_krw;lots=[];orders=[];equity=[];anchor=float(d.close.iloc[0]);prev=None;prev_ts=None;gaps=0;realized=0.
 fee=a.fee_bps/10000;slip=a.slippage_bps/10000
 for r in d.itertuples():
  gap=prev_ts is not None and (r.ts-prev_ts).total_seconds()>a.max_gap_minutes*60
  if gap:gaps+=1;anchor=float(r.close)
  if prev is not None and not gap:
   eligible=[(i,l) for i,l in enumerate(lots) if prev>=l["target"]]
   if eligible:
    i,lot=min(eligible,key=lambda x:x[1]["target"]);px=float(r.open)*(1-slip)
    proceeds=lot["qty"]*px*(1-fee);cash+=proceeds;profit=proceeds-lot["cost"];realized+=profit;lots.pop(i)
    orders.append(dict(ts=str(r.ts),side="SELL",price=px,qty=lot["qty"],pnl=profit))
   elif prev<=anchor*(1-a.grid_pct/100) and cash>=a.order_krw and sum(l["cost"] for l in lots)+a.order_krw<=a.initial_krw*a.max_exposure_pct/100:
    px=float(r.open)*(1+slip);qty=a.order_krw/(1+fee)/px;cash-=a.order_krw
    lots.append(dict(qty=qty,cost=a.order_krw,target=px*(1+a.take_profit_pct/100)))
    anchor*=1-a.grid_pct/100
    orders.append(dict(ts=str(r.ts),side="BUY",price=px,qty=qty,pnl=None))
  equity.append(dict(ts=str(r.ts),equity_krw=cash+sum(l["qty"]*float(r.close) for l in lots),cost_basis=sum(l["cost"] for l in lots)))
  prev=float(r.close);prev_ts=r.ts
 e=pd.DataFrame(equity);o=pd.DataFrame(orders);dest=Path(a.out).expanduser();dest.mkdir(parents=True,exist_ok=True)
 e.to_csv(dest/"equity.csv",index=False);o.to_csv(dest/"trades.csv",index=False)
 result=dict(label="RESEARCH_NEXT_OPEN_MARKET_PROXY",bars=len(d),first=str(d.ts.iloc[0]),last=str(d.ts.iloc[-1]),
 net_return=float(e.equity_krw.iloc[-1]/a.initial_krw-1),mdd=float((e.equity_krw/e.equity_krw.cummax()-1).min()),
 realized_pnl=float(realized),buys=sum(x["side"]=="BUY" for x in orders),sells=sum(x["side"]=="SELL" for x in orders),
 open_lots=len(lots),mean_exposure_pct=float(e.cost_basis.mean()/a.initial_krw*100),gaps=gaps,
 warnings="Next-open market proxy; not passive grid fill, no orderbook or latency; research only.")
 (dest/"summary.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="~/research/upbit_eth/krw_eth_1m.sqlite3")
 p.add_argument("--start",default="2026-07-01");p.add_argument("--end",default="2026-10-10")
 p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/grid_v2")
 for flag,default in [("initial-krw",1000000),("order-krw",10000),("grid-pct",.5),("take-profit-pct",.8),("max-exposure-pct",30),("fee-bps",5),("slippage-bps",2),("max-gap-minutes",3)]:p.add_argument("--"+flag,type=float,default=default)
 a=p.parse_args()
 if min(a.initial_krw,a.order_krw,a.grid_pct,a.take_profit_pct,a.max_exposure_pct,a.max_gap_minutes)<=0 or a.max_exposure_pct>100:p.error("Invalid parameters")
 run(a)
