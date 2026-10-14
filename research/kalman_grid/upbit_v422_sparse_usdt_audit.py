"""V4.22 offline ETH/USDT sparse-market liquidity diagnostics.
Public candle CSV only; no keys, network or orders. One trade-minute is not a fill.
"""
import argparse,csv,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from decimal import Decimal
from collections import Counter
D=Decimal
def parse(s):
 d=datetime.fromisoformat(s.replace("Z","+00:00"))
 return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--usdt-csv",required=True)
 p.add_argument("--krw-csv")
 p.add_argument("--start",required=True);p.add_argument("--end",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args();start=parse(a.start);end=parse(a.end)
 if not start<end:raise ValueError("BAD_WINDOW")
 def load(path):
  rows={}
  with open(path,newline="",encoding="utf-8-sig") as f:
   for r in csv.DictReader(f):
    t=parse(r["t"])
    if start<=t<end:
     if t in rows:raise ValueError("DUPLICATE_TIMESTAMP")
     rows[t]=r
  return rows
 u=load(a.usdt_csv)
 k=load(a.krw_csv) if a.krw_csv else {}
 minutes=int((end-start).total_seconds()//60)
 if not minutes or minutes>525600:raise ValueError("WINDOW_TOO_LARGE")
 timeline=[start+timedelta(minutes=i) for i in range(minutes)]
 blocks=[];consecutive=0
 for t in timeline:
  if t in u:
   if consecutive:blocks.append(consecutive);consecutive=0
  else:consecutive+=1
 if consecutive:blocks.append(consecutive)
 hourly=Counter(t.strftime("%Y-%m-%dT%H:00Z") for t in u)
 vals=[D(r["v"]) for r in u.values()]
 quote_turnover=sum((D(r["v"])*D(r["c"]) for r in u.values()),D(0))
 # Volume*close is a proxy, not actual traded quote turnover.
 comparative={"krw_candle_count":len(k),"overlap_candle_minutes":len(set(k)&set(u)),
  "usdt_only_minutes":len(set(u)-set(k))}
 report={"status":"SPARSE_MARKET_AUDIT","market":"USDT-ETH","start":start.isoformat(),"end":end.isoformat(),
 "window_minutes":minutes,"observed_trade_minutes":len(u),
 "observed_trade_minute_fraction":len(u)/minutes,"no_candle_minutes":minutes-len(u),
 "max_consecutive_no_candle_minutes":max(blocks,default=0),
 "hourly_trade_minute_counts":dict(sorted(hourly.items())),
 "total_base_volume_eth":str(sum(vals,D(0))),
 "estimated_quote_turnover_usdt_using_close":str(quote_turnover),
 "min_close_usdt":str(min((D(r["c"]) for r in u.values()),default=D(0))),
 "max_close_usdt":str(max((D(r["c"]) for r in u.values()),default=D(0))),
 "krw_comparison":comparative,
 "limitations":"Sparse minutes may be no-trade intervals; candle absence is not absence of orderbook liquidity. OHLCV alone does not establish ability to fill a limit order, bid/ask depth, or fee/FX parity."}
 out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
