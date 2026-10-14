#!/usr/bin/env python3
"""Read-only v5: drawdown circuit breaker applied to the frozen v3 mechanics.
Next-observed-open market proxy; no actual Upbit orders, no limit-order fill claims.
"""
import argparse, sqlite3, json
from pathlib import Path
import pandas as pd

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="~/research/upbit_eth/krw_eth_1m.sqlite3")
 p.add_argument("--start",default="2026-02-18")
 p.add_argument("--end",default="2026-07-01")
 p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/v5_dd")
 p.add_argument("--dd-stop-pct",type=float,default=5)
 p.add_argument("--cooldown-days",type=float,default=7)
 p.add_argument("--initial-krw",type=float,default=1000000)
 p.add_argument("--order-krw",type=float,default=10000)
 p.add_argument("--grid-pct",type=float,default=.5)
 p.add_argument("--take-profit-pct",type=float,default=.8)
 p.add_argument("--max-exposure-pct",type=float,default=20)
 p.add_argument("--fee-bps",type=float,default=5)
 p.add_argument("--slippage-bps",type=float,default=2)
 p.add_argument("--max-gap-minutes",type=float,default=3)
 a=p.parse_args()
 if not (0<a.dd_stop_pct<100 and a.cooldown_days>=0 and a.initial_krw>0 and a.order_krw>0 and a.grid_pct>0 and a.take_profit_pct>0 and 0<a.max_exposure_pct<=100 and a.order_krw<=a.initial_krw*a.max_exposure_pct/100 and min(a.fee_bps,a.slippage_bps)>=0):p.error("Bad parameter")
 conn=sqlite3.connect(f"file:{Path(a.db).expanduser()}?mode=ro",uri=True,timeout=20)
 conn.execute("PRAGMA query_only=ON")
 d=pd.read_sql_query("SELECT ts_utc,open,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",conn,params=(a.start,a.end))
 conn.close()
 if len(d)<100:raise SystemExit("INSUFFICIENT_BARS")
 d["ts"]=pd.to_datetime(d.ts_utc,utc=True);d=d.sort_values("ts").drop_duplicates("ts")
 if d[["open","close"]].isna().any().any() or (d[["open","close"]]<=0).any().any():raise ValueError("invalid market data")
 cash=a.initial_krw;lots=[];anchor=float(d.close.iloc[0]);highwater=a.initial_krw
 last_close=None;last_ts=None;cool_until=None;events=[];ledger=[];trips=0;gap_count=0
 fee=a.fee_bps/1e4;slip=a.slippage_bps/1e4
 for r in d.itertuples(index=False):
  gap=last_ts is not None and (r.ts-last_ts).total_seconds()>60*a.max_gap_minutes
  if gap:gap_count+=1;last_close=None;anchor=float(r.close)
  prior_equity=cash+sum(x["qty"]*last_close for x in lots) if last_close is not None else None
  # Check completed prior candle only. Liquidate all on next candle open after threshold breach.
  hit=last_close is not None and lots and prior_equity <= highwater*(1-a.dd_stop_pct/100)
  if hit:
   px=float(r.open)*(1-slip)
   for lot in lots:
    proceeds=lot["qty"]*px*(1-fee);cash+=proceeds
    events.append(dict(ts=str(r.ts),side="FORCED_EXIT",price=px,qty=lot["qty"],pnl=proceeds-lot["cost"]))
   lots=[];trips+=1
   cool_until=r.ts+pd.Timedelta(days=a.cooldown_days)
   anchor=float(r.open)
  elif last_close is not None:
   exits=[(i,lot) for i,lot in enumerate(lots) if last_close>=lot["target"]]
   if exits:
    idx,lot=min(exits,key=lambda x:x[1]["target"])
    px=float(r.open)*(1-slip);proceeds=lot["qty"]*px*(1-fee);cash+=proceeds;lots.pop(idx)
    events.append(dict(ts=str(r.ts),side="SELL",price=px,qty=lot["qty"],pnl=proceeds-lot["cost"]))
   elif (cool_until is None or r.ts>=cool_until) and last_close<=anchor*(1-a.grid_pct/100) and cash>=a.order_krw and sum(x["cost"] for x in lots)+a.order_krw<=a.initial_krw*a.max_exposure_pct/100+1e-8:
    px=float(r.open)*(1+slip);qty=a.order_krw/(1+fee)/px
    cash-=a.order_krw;lots.append(dict(qty=qty,cost=a.order_krw,target=px*(1+a.take_profit_pct/100)))
    events.append(dict(ts=str(r.ts),side="BUY",price=px,qty=qty,pnl=None));anchor=last_close
  anchor=max(anchor,float(r.close))
  eq=cash+sum(x["qty"]*float(r.close) for x in lots)
  highwater=max(highwater,eq)
  ledger.append(dict(ts=str(r.ts),equity_krw=eq,cost_basis=sum(x["cost"] for x in lots),cash_krw=cash,lots=len(lots),peak_krw=highwater))
  last_close=float(r.close);last_ts=r.ts
 e=pd.DataFrame(ledger);t=pd.DataFrame(events)
 dest=Path(a.out).expanduser();dest.mkdir(parents=True,exist_ok=True)
 e.to_csv(dest/"equity.csv",index=False);t.to_csv(dest/"trades.csv",index=False)
 z={"start":str(d.ts.iloc[0]),"end":str(d.ts.iloc[-1]),"bars":len(d),"net_return_pct":100*(e.equity_krw.iloc[-1]/a.initial_krw-1),
 "mdd_pct":100*(e.equity_krw/e.equity_krw.cummax()-1).min(),"trips":trips,
 "buys":int((t.side=="BUY").sum()) if len(t) else 0,"regular_sells":int((t.side=="SELL").sum()) if len(t) else 0,
 "forced_exit_lots":int((t.side=="FORCED_EXIT").sum()) if len(t) else 0,
 "forced_exit_realized_pnl_krw":float(t.loc[t.side=="FORCED_EXIT","pnl"].sum()) if len(t) else 0,
 "open_lots":len(lots),"mean_exposure_pct":100*e.cost_basis.mean()/a.initial_krw,
 "gap_count":gap_count,"dd_stop_pct":a.dd_stop_pct,"cooldown_days":a.cooldown_days,
 "limitations":"Trailing drawdown circuit breaker, not hard loss cap: next-open gaps can exceed threshold; OHLC-independent next-open proxy; no order book/ticks; same inspected sample, NOT OOS."}
 (dest/"summary.json").write_text(json.dumps(z,ensure_ascii=False,indent=2))
 print(json.dumps(z,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
