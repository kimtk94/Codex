"""Upbit public market snapshot recorder: GET-only, credentials-free, no trading.

Writes fresh bid/ask/ticker observations; does NOT simulate exchange fills.
"""
import argparse,csv,json,os,time,sys
from pathlib import Path
from datetime import datetime,timezone
from upbit_v47_public_connectivity import read

def once(markets):
    names=markets.split(",")
    ticks=read("/v1/ticker",{"markets":markets})
    books=read("/v1/orderbook",{"markets":markets,"count":5})
    ti={x["market"]:x for x in ticks};ob={x["market"]:x for x in books}
    records=[];now=datetime.now(timezone.utc).isoformat()
    for market in names:
        if market not in ti or market not in ob:raise ValueError("missing market "+market)
        bidask=ob[market]["orderbook_units"][0]
        bid=float(bidask["bid_price"]);ask=float(bidask["ask_price"])
        last=float(ti[market]["trade_price"])
        if not (bid>0 and ask>=bid and last>0):raise ValueError("invalid book "+market)
        records.append({"observed_at_utc":now,"market":market,
          "ticker_ts_ms":ti[market].get("timestamp"),"book_ts_ms":ob[market].get("timestamp"),
          "last_krw":last,"bid_krw":bid,"ask_krw":ask,
          "spread_krw":ask-bid,"spread_pct_mid":(ask-bid)/((ask+bid)/2)*100,
          "bid_size":bidask.get("bid_size"),"ask_size":bidask.get("ask_size")})
    return records

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--markets",default="KRW-ETH,KRW-BTC")
    p.add_argument("--samples",type=int,default=1)
    p.add_argument("--interval-seconds",type=float,default=10)
    a=p.parse_args()
    if a.samples<1 or a.samples>360:raise SystemExit("samples must be 1..360")
    if a.interval_seconds<1:raise SystemExit("interval must be >=1 seconds")
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    for i in range(a.samples):
        rows=once(a.markets)
        exists=path.exists() and path.stat().st_size>0
        with path.open("a",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]))
            if not exists:w.writeheader()
            w.writerows(rows)
        for row in rows:print(json.dumps(row,ensure_ascii=False),flush=True)
        if i+1<a.samples:time.sleep(a.interval_seconds)
    print(json.dumps({"status":"PUBLIC_GET_ONLY_COMPLETE","samples":a.samples,"csv":str(path)}))
if __name__=="__main__":sys.exit(main())
