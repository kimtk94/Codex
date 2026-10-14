"""V4.13 offline quote-cross PAPER replay. No broker, credentials, or orders.

Crossing is an optimistic indicative proxy, not proof of exchange fills.
Fixed vs conditional upward reanchor only when no inventory is held.
"""
import argparse,csv,json
from pathlib import Path
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING
D=Decimal
def snap(x,t,rounding):return (x/t).to_integral_value(rounding=rounding)*t
class Grid:
 def __init__(self,first,gap,depth,capital,order,fee,tick,policy,reanchor_pct):
  self.anchor=D(first);self.gap=D(gap)/100;self.depth=depth
  self.capital=D(capital);self.cash=self.capital;self.order=D(order)
  self.fee=D(fee)/100;self.tick=D(tick);self.policy=policy
  self.reanchor=D(reanchor_pct)/100;self.levels={};self.n_buy=0;self.n_sell=0
  self.events=[];self.peak=self.capital;self.mdd=D(0);self.high_inventory=0
  self.make_levels()
 def make_levels(self):
  self.levels={i:{"buy_limit":snap(self.anchor*(1-self.gap*i),self.tick,ROUND_FLOOR),"qty":D(0),"cost":D(0),"buy_fee":D(0),"target":D(0),"state":"WAIT_BUY"} for i in range(1,self.depth+1)}
 def step(self,row):
  ask=D(row["ask_krw"]);bid=D(row["bid_krw"]);ts=row["observed_at_utc"]
  if not (ask>=bid>0):raise ValueError("bad bid ask")
  if self.policy=="upward_idle" and all(x["state"]=="WAIT_BUY" for x in self.levels.values()) and ask>=self.anchor*(1+self.reanchor):
   self.anchor=ask;self.make_levels()
   self.events.append({"ts":ts,"event":"REANCHOR_UPWARD_IDLE","anchor":str(self.anchor)})
  for i,o in self.levels.items():
   if o["state"]=="WAIT_BUY" and ask<=o["buy_limit"]:
    # Immediate ask-cross proxy; fee included in funding check.
    buyfee=self.order*self.fee
    if self.cash<self.order+buyfee:continue
    qty=self.order/ask
    target=snap(ask*(1+self.gap),self.tick,ROUND_CEILING)
    if target<=ask:continue
    self.cash-=self.order+buyfee
    o.update(state="WAIT_SELL",qty=qty,cost=self.order,buy_fee=buyfee,target=target,entry_ts=ts)
    self.n_buy+=1;self.events.append({"ts":ts,"event":"INDICATIVE_BUY","level":i,"price":str(ask)})
   elif o["state"]=="WAIT_SELL" and ts!=o["entry_ts"] and bid>=o["target"]:
    proceeds=o["qty"]*bid;sf=proceeds*self.fee
    pnl=proceeds-sf-o["cost"]-o["buy_fee"];self.cash+=proceeds-sf
    self.n_sell+=1;self.events.append({"ts":ts,"event":"INDICATIVE_SELL","level":i,"price":str(bid),"net_krw":str(pnl)})
    o.update(state="WAIT_BUY",qty=D(0),cost=D(0),buy_fee=D(0),target=D(0),entry_ts=None)
  qty=sum((o["qty"] for o in self.levels.values()),D(0))
  inventory=sum(o["state"]=="WAIT_SELL" for o in self.levels.values())
  self.high_inventory=max(self.high_inventory,inventory)
  equity=self.cash+qty*bid
  self.peak=max(self.peak,equity)
  self.mdd=max(self.mdd,(self.peak-equity)/self.peak)
  self.equity=equity
 def result(self):
  inv=sum(o["state"]=="WAIT_SELL" for o in self.levels.values())
  return {"policy":self.policy,"gap_pct":str(self.gap*100),"buy_crosses":self.n_buy,"sell_crosses":self.n_sell,
    "open_lots":inv,"max_open_lots":self.high_inventory,"cash_krw":str(self.cash),
    "equity_bid_mark_krw":str(self.equity),"return_pct":str((self.equity/self.capital-1)*100),
    "mdd_pct":str(self.mdd*100),"reanchors":sum(e["event"]=="REANCHOR_UPWARD_IDLE" for e in self.events)}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--csv",required=True);p.add_argument("--out",required=True)
 p.add_argument("--gaps",default="0.15,0.18,0.21");p.add_argument("--policies",default="fixed,upward_idle")
 p.add_argument("--reanchor-pct",default="0.5")
 p.add_argument("--cash",default="1000000");p.add_argument("--notional",default="5500")
 p.add_argument("--fee",default="0.05");p.add_argument("--tick",default="1000");p.add_argument("--depth",type=int,default=30)
 a=p.parse_args()
 with open(a.csv,newline="") as f:rows=[r for r in csv.DictReader(f) if r["market"]=="KRW-ETH"]
 if len(rows)<2:raise SystemExit("NEED_AT_LEAST_TWO_QUOTES")
 if D(a.cash)<=0 or D(a.notional)<5000 or D(a.fee)<0 or D(a.tick)<=0:raise SystemExit("BAD_CONFIG")
 if a.depth<1 or a.depth>300:raise SystemExit("BAD_DEPTH")
 if any(D(v)<=0 for v in a.gaps.split(",")):raise SystemExit("BAD_GAPS")
 grids=[Grid(rows[0]["ask_krw"],g,a.depth,a.cash,a.notional,a.fee,a.tick,policy,a.reanchor_pct) for policy in a.policies.split(",") for g in a.gaps.split(",")]
 for row in rows:
  for grid in grids:grid.step(row)
 result={"mode":"OFFLINE_QUOTE_CROSS_PAPER_ONLY","market":"KRW-ETH","samples":len(rows),
 "results":[g.result() for g in grids],
 "limitations":"Observed best bid/ask crossing is optimistic; no intra-sample path, passive queue priority, partial fills, real exchange fills, latency, or live capital commitments. Upward reanchor only if completely flat, by design."}
 dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2,ensure_ascii=False))
 print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
