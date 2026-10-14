#!/usr/bin/env python3
"""Upbit KRW-ETH v4 research: prior CLOSED UTC day momentum gate on v3.
Read-only SQLite; next open simulated execution; NOT a passive limit fill."""
import argparse,sqlite3,json
from pathlib import Path
import pandas as pd

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="~/research/upbit_eth/krw_eth_1m.sqlite3")
 p.add_argument("--start",default="2026-07-01")
 p.add_argument("--end",default="2026-10-10")
 p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/grid_v4_gate")
 for k,v in (("initial-krw",1000000),("order-krw",10000),("grid-pct",.5),("take-profit-pct",.8),("max-exposure-pct",20),("fee-bps",5),("slippage-bps",2),("max-gap-minutes",3),("momentum-days",14),("stop-entry-return-pct",-5)):
  p.add_argument("--"+k,type=float if k not in ("momentum-days",) else int,default=v)
 a=p.parse_args()
 if not (a.initial_krw>0 and a.order_krw>0 and a.grid_pct>0 and a.take_profit_pct>0 and 0<a.max_exposure_pct<=100 and a.momentum_days>=2):p.error("Invalid parameter")
 # Fetch pre-window history to construct prior-close-only daily signal.
 con=sqlite3.connect(f"file:{Path(a.db).expanduser()}?mode=ro",uri=True,timeout=20)
 con.execute("PRAGMA query_only=ON")
 history_start=str((pd.Timestamp(a.start,tz="UTC")-pd.Timedelta(days=a.momentum_days+10)).date())
 df=pd.read_sql_query("SELECT ts_utc,open,high,low,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",con,params=(history_start,a.end));con.close()
 df["ts"]=pd.to_datetime(df.ts_utc,utc=True)
 df=df.sort_values("ts").drop_duplicates("ts")
 if len(df)<100:raise SystemExit("INSUFFICIENT_DATA")
 # Daily close at last observed minute of UTC day. A gate for day D only uses <=D-1 closes.
 day=df.ts.dt.floor("D")
 daily=df.groupby(day).agg(close=("close","last"),bars=("close","size"))
 # Reject days with severe missing data for gating: no inference from <95% observed minutes.
 daily["usable"]=daily.bars>=1368
 daily["mom"]=daily.close/daily.close.shift(a.momentum_days)-1
 valid=daily.usable & daily.usable.shift(a.momentum_days).fillna(False)
 daily.loc[~valid,"mom"]=float("nan")
 prior_mom=daily.mom.shift(1)
 prior_valid=daily.usable.shift(1).fillna(False)
 gate=dict(zip(daily.index,zip(prior_mom,prior_valid)))
 trade=df[(df.ts>=pd.Timestamp(a.start,tz="UTC"))&(df.ts<pd.Timestamp(a.end,tz="UTC"))]
 if len(trade)<100:raise SystemExit("INSUFFICIENT_TEST_BARS")
 fee=a.fee_bps/10000;slip=a.slippage_bps/10000
 cash=a.initial_krw;lots=[];anchor=float(trade.close.iloc[0]);last_close=None;last_ts=None;events=[];ledger=[];blocked=0;unknown=0;gaps=0;realized=0.
 for r in trade.itertuples(index=False):
  gap=last_ts is not None and (r.ts-last_ts).total_seconds()>a.max_gap_minutes*60
  if gap:gaps+=1;last_close=None;anchor=float(r.close)
  mom,prior_ok=gate.get(r.ts.floor("D"),(float("nan"),False))
  entry_ok=bool(prior_ok and pd.notna(mom) and mom*100>a.stop_entry_return_pct)
  if not entry_ok:blocked+=1
  if pd.isna(mom):unknown+=1
  if last_close is not None:
   candidates=[(i,lot) for i,lot in enumerate(lots) if last_close>=lot["target"]]
   if candidates:
    i,lot=min(candidates,key=lambda x:x[1]["target"])
    price=float(r.open)*(1-slip);proceeds=lot["qty"]*price*(1-fee);profit=proceeds-lot["cost"]
    cash+=proceeds;realized+=profit;events.append(dict(ts=str(r.ts),side="SELL",pnl=profit,price=price,qty=lot["qty"]));lots.pop(i)
   elif entry_ok and last_close<=anchor*(1-a.grid_pct/100) and cash>=a.order_krw and sum(x["cost"] for x in lots)+a.order_krw<=a.initial_krw*a.max_exposure_pct/100+1e-8:
    price=float(r.open)*(1+slip);qty=a.order_krw/(1+fee)/price;cash-=a.order_krw
    lots.append(dict(cost=a.order_krw,qty=qty,target=price*(1+a.take_profit_pct/100)))
    anchor=last_close;events.append(dict(ts=str(r.ts),side="BUY",pnl=None,price=price,qty=qty))
  anchor=max(anchor,float(r.close))
  ledger.append(dict(ts=str(r.ts),equity_krw=cash+sum(x["qty"]*float(r.close) for x in lots),cost_basis=sum(x["cost"] for x in lots),can_enter=entry_ok))
  last_close=float(r.close);last_ts=r.ts
 e=pd.DataFrame(ledger);out=Path(a.out).expanduser();out.mkdir(parents=True,exist_ok=True)
 e.to_csv(out/"equity.csv",index=False);pd.DataFrame(events).to_csv(out/"trades.csv",index=False)
 stats=dict(model="EXPLORATORY_V4_PRIOR_DAY_MOMENTUM_GATE",bars=len(trade),first=str(trade.ts.iloc[0]),last=str(trade.ts.iloc[-1]),net_return=float(e.equity_krw.iloc[-1]/a.initial_krw-1),mdd=float((e.equity_krw/e.equity_krw.cummax()-1).min()),buys=sum(x["side"]=="BUY" for x in events),sells=sum(x["side"]=="SELL" for x in events),open_lots=len(lots),realized_pnl=realized,mean_exposure_pct=float(e.cost_basis.mean()/a.initial_krw*100),blocked_bar_pct=100*blocked/len(trade),unknown_gate_bars=unknown,gaps=gaps,gate_window_days=a.momentum_days,entry_stop_pct=a.stop_entry_return_pct,limitations="Market next-open proxy, partial daily missing data; 2026 known exploratory sample, not unbiased OOS; terminal inventory marked at close without liquidation charge")
 (out/"summary.json").write_text(json.dumps(stats,indent=2));print(json.dumps(stats,indent=2))
if __name__=="__main__":main()
