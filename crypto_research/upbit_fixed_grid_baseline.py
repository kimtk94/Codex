#!/usr/bin/env python3
"""Read-only KRW-ETH one-minute fixed-grid baseline, research only.
Conservative: one fill per minute, no same-candle round trip; gap >3 min blocks fill.
No live orders, no interpolation, no set -e.
"""
import argparse, sqlite3, json
from pathlib import Path
import numpy as np
import pandas as pd

def run(args):
    db=Path(args.db).expanduser()
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True,timeout=20)
    con.execute("PRAGMA query_only=ON")
    q="SELECT ts_utc,open,high,low,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc"
    df=pd.read_sql_query(q,con,params=(args.start,args.end))
    con.close()
    if len(df)<100: raise ValueError("Too few candles")
    df["ts"]=pd.to_datetime(df.ts_utc,utc=True)
    df=df.dropna().drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    for c in ("open","high","low","close"): df[c]=pd.to_numeric(df[c],errors="coerce")
    if df[["open","high","low","close"]].isna().any().any(): raise ValueError("Invalid OHLC")
    if (df[["open","high","low","close"]]<=0).any().any(): raise ValueError("Nonpositive OHLC")
    start_cash=float(args.initial_krw)
    cash=start_cash
    units=0.0
    buy_anchor=float(df.close.iloc[0])
    sell_anchor=None
    initial_reference=buy_anchor
    trades=[]; equity=[]; skipped=0
    fee=args.fee_bps/10000
    slip=args.slippage_bps/10000
    gap_trigger=pd.Timedelta(minutes=args.max_gap_minutes)
    for i,row in enumerate(df.itertuples()):
        discontinuity=(i>0 and row.ts-df.ts.iloc[i-1]>gap_trigger)
        if discontinuity:
            skipped+=1
            # Reset ladder anchors to the newly observed close.
            buy_anchor=float(row.close)
            if units>0: sell_anchor=max(float(row.close), float(sell_anchor or row.close))
        elif i:
            # One order per observed candle, conservative limit-like OHLC touch.
            # Buy at next lower ladder; require observed low and a non-gapped candle.
            target=buy_anchor*(1-args.grid_pct/100)
            if row.low<=target and cash>=args.order_krw:
                execution=min(float(row.open),target)*(1+slip)
                gross=args.order_krw/(1+fee)
                qty=gross/execution
                cash-=args.order_krw
                units+=qty
                buy_anchor=target
                # sell at a profitable target after fees, not in this candle
                if sell_anchor is None: sell_anchor=execution*(1+args.take_profit_pct/100)
                trades.append({"ts":str(row.ts),"side":"BUY","price":execution,"quantity":qty,"cash":cash})
            elif units>0 and sell_anchor is not None and row.high>=sell_anchor:
                # Sell *all* inventory on a target touch (not necessarily profitable).
                execution=max(float(row.open),sell_anchor)*(1-slip)
                cash+=units*execution*(1-fee)
                trades.append({"ts":str(row.ts),"side":"SELL","price":execution,"quantity":units,"cash":cash})
                units=0.0
                buy_anchor=float(row.close)
                sell_anchor=None
        equity.append(cash+units*float(row.close))
    curve=pd.Series(equity,dtype=float)
    mdd=float((curve/curve.cummax()-1).min())
    ret=float(curve.iloc[-1]/start_cash-1)
    buyhold=float(df.close.iloc[-1]/initial_reference-1)
    dest=Path(args.out).expanduser();dest.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(trades).to_csv(dest/"trades.csv",index=False)
    pd.DataFrame({"ts":df.ts.astype(str),"equity_krw":equity}).to_csv(dest/"equity.csv",index=False)
    result={"label":"RESEARCH_BASELINE_NOT_LIVE","start":str(df.ts.iloc[0]),"end":str(df.ts.iloc[-1]),
        "bars":len(df),"gap_events_skipped":skipped,"trades":len(trades),
        "final_equity_krw":float(curve.iloc[-1]),"net_return":ret,"mdd":mdd,
        "underlying_buyhold_return":buyhold,
        "limitations":"OHLC-touch optimistic for passive order queue and same-minute price path; one order per candle; no live fills; variable spread/tick sizes not modeled; inventory sell target anchored to first buy, not weighted average; no capital recycling optimization."}
    (dest/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="~/research/upbit_eth/krw_eth_1m.sqlite3")
    p.add_argument("--start",default="2026-07-01")
    p.add_argument("--end",default="2026-10-10")
    p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/baseline")
    p.add_argument("--initial-krw",type=float,default=1000000)
    p.add_argument("--order-krw",type=float,default=10000)
    p.add_argument("--grid-pct",type=float,default=.5)
    p.add_argument("--take-profit-pct",type=float,default=.8)
    p.add_argument("--fee-bps",type=float,default=5)
    p.add_argument("--slippage-bps",type=float,default=2)
    p.add_argument("--max-gap-minutes",type=float,default=3)
    a=p.parse_args()
    if min(a.initial_krw,a.order_krw,a.grid_pct,a.take_profit_pct)<=0: p.error("positive parameters required")
    run(a)
if __name__=="__main__":main()
