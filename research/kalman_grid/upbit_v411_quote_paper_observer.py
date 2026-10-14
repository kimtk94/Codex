"""V4.11 quote-based PAPER observation, NEVER sends orders.

Entry at fixed initially observed reference minus one step; fill is only
'cross-observed' if best ask <= limit. Exit when best bid >= target.
No queue evidence: both are indicative fills, not executable confirmations.
"""
import argparse,csv,json,sys,time
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING
from pathlib import Path
from upbit_v48_public_market_recorder import once
D=Decimal
def floor_tick(p,tick):return (p/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
def ceil_tick(p,tick):return (p/tick).to_integral_value(rounding=ROUND_CEILING)*tick

class Observer:
 def __init__(self,anchor,spacing,depth=30,notional=D("5500"),fee=D("0.05"),tick=D("1000")):
  self.anchor=D(str(anchor));self.spacing=D(str(spacing))/100;self.depth=depth
  self.notional=notional;self.fee=fee/100;self.tick=tick
  self.orders={k:{"entry":floor_tick(self.anchor*(1-self.spacing*k),tick),"state":"WAIT_BUY","entry_time":None} for k in range(1,depth+1)}
  self.events=[];self.last=None
 def on_quote(self,row):
  ask=D(str(row["ask_krw"]));bid=D(str(row["bid_krw"]));ts=row["observed_at_utc"]
  if ask<bid or bid<=0:raise ValueError("bad book")
  self.last=row
  for level,o in self.orders.items():
   if o["state"]=="WAIT_BUY" and ask<=o["entry"]:
    o.update(state="WAIT_SELL",entry_time=ts,fill_price=ask,qty=self.notional/ask,
      target=ceil_tick(ask*(1+self.spacing),self.tick))
    self.events.append({"at_utc":ts,"event":"INDICATIVE_BUY_CROSS","level":level,"price":str(ask)})
   elif o["state"]=="WAIT_SELL" and ts!=o["entry_time"] and bid>=o["target"]:
    gross=o["qty"]*bid-self.notional
    fees=self.notional*self.fee+(o["qty"]*bid)*self.fee
    pnl=gross-fees
    self.events.append({"at_utc":ts,"event":"INDICATIVE_SELL_CROSS","level":level,"price":str(bid),"net_krw":str(pnl)})
    o.update(state="CLOSED",net_krw=pnl)
 def result(self):
  done=[x["net_krw"] for x in self.orders.values() if x["state"]=="CLOSED"]
  return {"mode":"PAPER_QUOTE_CROSS_ONLY","anchor_krw":str(self.anchor),
   "spacing_pct":str(self.spacing*100),"depth":self.depth,"observed_buy_crosses":sum(x["event"]=="INDICATIVE_BUY_CROSS" for x in self.events),
   "observed_sell_crosses":len(done),"indicative_realized_net_krw":str(sum(done,D(0))),
   "unclosed_buy_lots":sum(o["state"]=="WAIT_SELL" for o in self.orders.values()),
   "not_filled_buy_levels":sum(o["state"]=="WAIT_BUY" for o in self.orders.values()),
   "warning":"Snapshot crossing only; no order book queue, partial fills, real order placement, or execution proof"}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--quotes",help="Existing V48 quote CSV, no new API requests")
 p.add_argument("--samples",type=int,default=1)
 p.add_argument("--interval",type=float,default=2)
 p.add_argument("--gaps",default="0.15,0.18,0.21")
 p.add_argument("--depth",type=int,default=30)
 p.add_argument("--notional",default="5500")
 p.add_argument("--fee",default="0.05")
 p.add_argument("--out",required=True)
 a=p.parse_args()
 if a.depth<1 or a.depth>100 or a.samples<1 or a.samples>120 or a.interval<1: p.error("invalid depth/samples/interval")
 if a.quotes:
  with open(a.quotes,newline="") as f: rows=[r for r in csv.DictReader(f) if r["market"]=="KRW-ETH"]
 else:
  rows=[]
  for i in range(a.samples):
   rows.extend(r for r in once("KRW-ETH") if r["market"]=="KRW-ETH")
   if i+1<a.samples:time.sleep(a.interval)
 if not rows:raise SystemExit("NO_ETH_QUOTES")
 runners=[Observer(rows[0]["ask_krw"],x,a.depth,D(a.notional),D(a.fee)) for x in a.gaps.split(",")]
 for row in rows:
  for runner in runners:runner.on_quote(row)
 result={"samples":len(rows),"market":"KRW-ETH","results":[r.result() for r in runners],
  "events":[{"spacing_pct":str(r.spacing*100),**e} for r in runners for e in r.events]}
 dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({"samples":len(rows),"results":result["results"],"out":str(dest)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
