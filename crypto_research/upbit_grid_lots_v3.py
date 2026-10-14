#!/usr/bin/env python3
"""Upbit KRW-ETH grid v3: read-only, conservative next-open proxy research."""
import argparse, json, sqlite3
from pathlib import Path
import pandas as pd

def simulate(df, a):
    fee=a.fee_bps/10000; slip=a.slippage_bps/10000
    cash=a.initial_krw; lots=[]; anchor=float(df.iloc[0].close)
    prev=None; prev_ts=None; gap_count=0; realized=0.0; events=[]; curve=[]
    for r in df.itertuples(index=False):
        gap=prev_ts is not None and (r.ts-prev_ts).total_seconds()>60*a.max_gap_minutes
        if gap:
            gap_count+=1; prev=None; anchor=float(r.close)
        # All decisions use the previous observed close, executed at next open.
        # Never invent fills in missing bars; one fill per candle.
        if prev is not None:
            exits=[(i,l) for i,l in enumerate(lots) if prev>=l["target"]]
            if exits:
                i,lot=min(exits,key=lambda x:x[1]["target"])
                px=float(r.open)*(1-slip)
                proceeds=lot["qty"]*px*(1-fee)
                cash+=proceeds; realized+=proceeds-lot["cost"]
                events.append(dict(ts=str(r.ts),side="SELL",price=px,qty=lot["qty"],net_pnl=proceeds-lot["cost"]))
                lots.pop(i)
            elif prev<=anchor*(1-a.grid_pct/100) and cash>=a.order_krw and sum(l["cost"] for l in lots)+a.order_krw<=a.initial_krw*a.max_exposure_pct/100+1e-8:
                px=float(r.open)*(1+slip)
                qty=a.order_krw/(1+fee)/px
                cash-=a.order_krw
                lots.append(dict(qty=qty,cost=a.order_krw,target=px*(1+a.take_profit_pct/100)))
                events.append(dict(ts=str(r.ts),side="BUY",price=px,qty=qty,net_pnl=None))
                anchor=prev
        # Recenter only upward and only from observed close (no lookahead);
        # it permits new entries after rebounds, without cancelling open lots.
        anchor=max(anchor,float(r.close))
        equity=cash+sum(l["qty"]*float(r.close) for l in lots)
        curve.append(dict(ts=str(r.ts),equity_krw=equity,capital_krw=sum(l["cost"] for l in lots),cash_krw=cash,open_lots=len(lots)))
        prev=float(r.close);prev_ts=r.ts
    e=pd.DataFrame(curve)
    result=dict(bars=len(df),from_utc=str(df.ts.iloc[0]),to_utc=str(df.ts.iloc[-1]),
       initial_krw=a.initial_krw,final_equity_krw=float(e.equity_krw.iloc[-1]),
       net_return=float(e.equity_krw.iloc[-1]/a.initial_krw-1),
       mdd=float((e.equity_krw/e.equity_krw.cummax()-1).min()),
       buys=sum(x["side"]=="BUY" for x in events),sells=sum(x["side"]=="SELL" for x in events),
       open_lots=len(lots),realized_pnl_krw=realized,
       exposure_mean_pct=float(e.capital_krw.mean()/a.initial_krw*100),
       exposure_max_pct=float(e.capital_krw.max()/a.initial_krw*100),
       cash_min_krw=float(e.cash_krw.min()),gaps_skipped=gap_count,
       model="NEXT_OPEN_MARKET_ORDER_PROXY_NON_LIVE",
       limits="Does not model passive limit fills, fee tier, tick size, spread or latency. Not an executable grid replica.")
    return result,pd.DataFrame(events),e

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="~/research/upbit_eth/krw_eth_1m.sqlite3")
    p.add_argument("--start",default="2026-07-01")
    p.add_argument("--end",default="2026-10-10")
    p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/grid_v3")
    for k,v in (("initial-krw",1000000),("order-krw",10000),("grid-pct",.5),("take-profit-pct",.8),("max-exposure-pct",30),("fee-bps",5),("slippage-bps",2),("max-gap-minutes",3)):
        p.add_argument("--"+k,type=float,default=v)
    a=p.parse_args()
    if min(a.initial_krw,a.order_krw,a.grid_pct,a.take_profit_pct,a.max_exposure_pct,a.max_gap_minutes)<=0 or a.max_exposure_pct>100 or a.order_krw>a.initial_krw*a.max_exposure_pct/100 or min(a.fee_bps,a.slippage_bps)<0:
        p.error("Invalid parameters")
    con=sqlite3.connect(f"file:{Path(a.db).expanduser()}?mode=ro",uri=True,timeout=20)
    con.execute("PRAGMA query_only=ON")
    df=pd.read_sql_query("SELECT ts_utc,open,high,low,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",con,params=(a.start,a.end))
    con.close()
    if len(df)<100:raise ValueError("insufficient candles")
    df["ts"]=pd.to_datetime(df.ts_utc,utc=True,errors="raise")
    df=df.sort_values("ts").drop_duplicates("ts")
    if df[["open","high","low","close"]].isna().any().any() or (df[["open","high","low","close"]]<=0).any().any():raise ValueError("invalid OHLC")
    result,trades,equity=simulate(df,a)
    target=Path(a.out).expanduser();target.mkdir(parents=True,exist_ok=True)
    trades.to_csv(target/"trades.csv",index=False)
    equity.to_csv(target/"equity.csv",index=False)
    (target/"summary.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
