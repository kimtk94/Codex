#!/usr/bin/env python3
"""Research-only v5 highwater-reset comparison. Reads Upbit SQLite read-only."""
import argparse,sqlite3,json
from pathlib import Path
import pandas as pd
def main():
 p=argparse.ArgumentParser()
 for k,v in [("db","~/research/upbit_eth/krw_eth_1m.sqlite3"),("start","2026-02-18"),("end","2026-07-01"),("out","~/ETH_REGIME_RESEARCH_20261014/v5_reset")]:p.add_argument("--"+k,default=v)
 for k,v in [("dd-stop-pct",3),("cooldown-days",7),("initial-krw",1000000),("order-krw",10000),("grid-pct",.5),("take-profit-pct",.8),("max-exposure-pct",20),("fee-bps",5),("slippage-bps",2),("max-gap-minutes",3)]:p.add_argument("--"+k,type=float,default=v)
 a=p.parse_args()
 con=sqlite3.connect(f"file:{Path(a.db).expanduser()}?mode=ro",uri=True);con.execute("PRAGMA query_only=ON")
 d=pd.read_sql_query("SELECT ts_utc,open,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",con,params=(a.start,a.end));con.close()
 d["ts"]=pd.to_datetime(d.ts_utc,utc=True);d=d.sort_values("ts").drop_duplicates("ts")
 if len(d)<100:raise ValueError("insufficient bars")
 cash=a.initial_krw;lots=[];anchor=float(d.close.iloc[0]);risk_peak=a.initial_krw;report_peak=a.initial_krw
 fee=a.fee_bps/10000;slip=a.slippage_bps/10000;cool_until=None;last_close=None;last_ts=None
 trades=[];curve=[];trip_times=[];gaps=0
 for r in d.itertuples(index=False):
  gap=last_ts is not None and (r.ts-last_ts).total_seconds()>60*a.max_gap_minutes
  if gap:gaps+=1;last_close=None;anchor=float(r.close)
  prior_equity=cash+sum(l["qty"]*last_close for l in lots) if last_close is not None else None
  hit=last_close is not None and bool(lots) and prior_equity<=risk_peak*(1-a.dd_stop_pct/100)
  if hit:
   price=float(r.open)*(1-slip)
   for l in lots:
    proceeds=l["qty"]*price*(1-fee);cash+=proceeds
    trades.append(dict(ts=str(r.ts),side="FORCED_EXIT",pnl=proceeds-l["cost"],qty=l["qty"]))
   lots=[];trip_times.append(str(r.ts));cool_until=r.ts+pd.Timedelta(days=a.cooldown_days)
   anchor=float(r.open)
   # RESET local breaker reference after exits; preserve actual portfolio peak separately.
   risk_peak=cash
  elif last_close is not None:
   exits=[(i,l) for i,l in enumerate(lots) if last_close>=l["target"]]
   if exits:
    i,l=min(exits,key=lambda x:x[1]["target"]);price=float(r.open)*(1-slip)
    proceeds=l["qty"]*price*(1-fee);cash+=proceeds;lots.pop(i)
    trades.append(dict(ts=str(r.ts),side="SELL",pnl=proceeds-l["cost"],qty=l["qty"]))
   elif (cool_until is None or r.ts>=cool_until) and last_close<=anchor*(1-a.grid_pct/100) and cash>=a.order_krw and sum(x["cost"] for x in lots)+a.order_krw<=a.initial_krw*a.max_exposure_pct/100+1e-8:
    price=float(r.open)*(1+slip);qty=a.order_krw/(1+fee)/price;cash-=a.order_krw
    lots.append(dict(qty=qty,cost=a.order_krw,target=price*(1+a.take_profit_pct/100)))
    trades.append(dict(ts=str(r.ts),side="BUY",pnl=None,qty=qty));anchor=last_close
  anchor=max(anchor,float(r.close))
  equity=cash+sum(l["qty"]*float(r.close) for l in lots)
  risk_peak=max(risk_peak,equity)
  report_peak=max(report_peak,equity)
  curve.append(dict(ts=str(r.ts),equity_krw=equity,cost_basis=sum(l["cost"] for l in lots),risk_peak=risk_peak,report_peak=report_peak))
  last_close=float(r.close);last_ts=r.ts
 e=pd.DataFrame(curve);t=pd.DataFrame(trades)
 out=Path(a.out).expanduser();out.mkdir(parents=True,exist_ok=True)
 e.to_csv(out/"equity.csv",index=False);t.to_csv(out/"trades.csv",index=False)
 s={"model":"V5_RESET_LOCAL_PEAK_RESEARCH","start":str(d.ts.iloc[0]),"end":str(d.ts.iloc[-1]),"bars":len(d),"net_return_pct":100*(e.equity_krw.iloc[-1]/a.initial_krw-1),"mdd_pct":100*(e.equity_krw/e.equity_krw.cummax()-1).min(),"trips":len(trip_times),"trip_times":trip_times,"forced_exit_lots":int((t.side=="FORCED_EXIT").sum()) if len(t) else 0,"forced_exit_pnl_krw":float(t.loc[t.side=="FORCED_EXIT","pnl"].sum()) if len(t) else 0,"buys":int((t.side=="BUY").sum()) if len(t) else 0,"sells":int((t.side=="SELL").sum()) if len(t) else 0,"open_lots":len(lots),"mean_exposure_pct":100*e.cost_basis.mean()/a.initial_krw,"gaps":gaps,"warning":"Same explored sample, no true OOS. Next-open proxy, not exchange execution. DD threshold not guaranteed during gaps."}
 (out/"summary.json").write_text(json.dumps(s,indent=2));print(json.dumps(s,indent=2))
if __name__=="__main__":main()
