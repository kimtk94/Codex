"""Fast public-only Upbit grid quote diagnostic. No API keys, orders or server config."""
import argparse,json,statistics,time
from datetime import datetime,timezone
from upbit_v48_public_market_recorder import once

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--samples",type=int,default=6)
 p.add_argument("--interval",type=float,default=2)
 p.add_argument("--markets",default="KRW-ETH,KRW-BTC")
 a=p.parse_args()
 if not 1<=a.samples<=30 or not 0<=a.interval<=30: p.error("samples 1..30, interval 0..30")
 data={}
 for n in range(a.samples):
  for r in once(a.markets):
   data.setdefault(r["market"],[]).append(r)
  if n+1<a.samples:time.sleep(a.interval)
 for market,rows in sorted(data.items()):
  spreads=[r["spread_pct_mid"] for r in rows]
  bid=rows[-1]["bid_krw"];ask=rows[-1]["ask_krw"]
  print(json.dumps({"market":market,"mode":"PUBLIC_GET_ONLY","samples":len(rows),
   "last_bid_krw":bid,"last_ask_krw":ask,
   "spread_pct_min":min(spreads),"spread_pct_median":statistics.median(spreads),
   "spread_pct_max":max(spreads),"quote_age_ms":max(0,int(datetime.now(timezone.utc).timestamp()*1000)-int(rows[-1]["book_ts_ms"] or 0)),
   "grid_spacing_pct":0.18,"grid_step_krw_reference":rows[-1]["last_krw"]*.0018,
   "status":"PASS" if bid>0 and ask>=bid else "FAIL"},ensure_ascii=False))
if __name__=="__main__":main()
