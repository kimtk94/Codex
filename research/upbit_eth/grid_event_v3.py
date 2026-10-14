#!/usr/bin/env python3
"""Read-only grid event research. Conservative OHLC fills, balance reservations; not live ready."""
import argparse,csv,datetime as dt,json,math,sqlite3
from pathlib import Path
def sim(c,y,space,n,capital,fee):
 kst=dt.timezone(dt.timedelta(hours=9))
 utc=lambda d:dt.datetime(d,1,1,tzinfo=kst).astimezone(dt.timezone.utc).isoformat()
 cur=iter(c.execute("SELECT ts_utc,high,low,close FROM candles WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc",(utc(y),utc(y+1))))
 first=next(cur,None)
 if not first:return None
 anchor=first[3];krw=capital/2;eth=capital/2/anchor;hold_krw=hold_eth=0.
 orders={};fills=ambiguous=gaps=0;fees=0.;peak=capital;mdd=0.;turnover=0.
 unit=capital/n
 def price(v,side):
  # All sampled KRW-ETH prices >=2m use 1000 KRW tick in these periods.
  tick=1000 if v>=2000000 else (500 if v>=1000000 else 100)
  return (math.floor(v/tick) if side=="B" else math.ceil(v/tick))*tick
 def add(side,p,amount):
  nonlocal krw,eth,hold_krw,hold_eth
  p=price(p,side);key=(side,p)
  if side=="B":
   if amount<5000 or krw+1e-8<amount*(1+fee):return
   krw-=amount*(1+fee);hold_krw+=amount*(1+fee)
  else:
   if p*amount<5000 or eth+1e-12<amount:return
   eth-=amount;hold_eth+=amount
  orders[key]=orders.get(key,0)+amount
 def cancel():
  nonlocal krw,eth,hold_krw,hold_eth
  for (side,p),v in orders.items():
   if side=="B":krw+=v*(1+fee);hold_krw-=v*(1+fee)
   else:eth+=v;hold_eth-=v
  orders.clear()
 def seed(center):
  for i in range(1,n//2+1):
   add("B",center/(1+space)**i,unit)
   add("S",center*(1+space)**i,unit/center)
 seed(anchor);prev=dt.datetime.fromisoformat(first[0]);last=anchor
 for stamp,high,low,close in cur:
  t=dt.datetime.fromisoformat(stamp)
  if (t-prev).total_seconds()>300:
   gaps+=1;cancel();seed(close)
   # First candle after data gap cannot be used for fill inference.
   prev=t;last=close;continue
  prev=t
  bs=[key for key in orders if key[0]=="B" and low<key[1]]
  ss=[key for key in orders if key[0]=="S" and high>key[1]]
  pending=[]
  if bs and ss:ambiguous+=1
  else:
   for side,touched in (("B",bs),("S",ss)):
    for key in sorted(touched,key=lambda z:z[1],reverse=(side=="B")):
     amount=orders.pop(key);px=key[1]
     if side=="B":
      hold_krw-=amount*(1+fee);eth+=amount/px
      fees+=amount*fee;turnover+=amount
      pending.append(("S",px*(1+space),amount/px))
     else:
      hold_eth-=amount;krw+=amount*px*(1-fee)
      fees+=amount*px*fee;turnover+=amount*px
      pending.append(("B",px/(1+space),amount*px/(1+fee)))
     fills+=1
   for side,px,amount in pending:add(side,px,amount)
  if min(krw,eth,hold_krw,hold_eth)<-1e-5:raise RuntimeError("balance invariant")
  equity=krw+hold_krw+(eth+hold_eth)*close
  peak=max(peak,equity);mdd=min(mdd,equity/peak-1);last=close
 equity=krw+hold_krw+(eth+hold_eth)*last
 return dict(year=y,spacing_pct=space*100,levels=n,return_pct=round(100*(equity/capital-1),4),mdd_pct=round(100*mdd,4),fills=fills,ambiguous_bars=ambiguous,gap_resets=gaps,fees_krw=round(fees,2),turnover_krw=round(turnover,2),benchmark_pct=round(100*(last/anchor-1),4))
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="krw_eth_1m.sqlite3");p.add_argument("--out",default="results_event_v3")
 p.add_argument("--capital",type=float,default=1000000);p.add_argument("--fee",type=float,default=.001)
 a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 con=sqlite3.connect("file:"+str(Path(a.db).resolve())+"?mode=ro",uri=True)
 con.execute("PRAGMA query_only=ON");rows=[]
 for y in (2024,2025,2026):
  for s in (.006,.01,.015):
   for n in (20,50,100):
    r=sim(con,y,s,n,a.capital,a.fee);rows.append(r);print(json.dumps(r),flush=True)
 with (out/"grid_event_results.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print("RESEARCH_ONLY: OHLC does not prove queue fills. Tick rules below KRW 2m are approximations; inspect every order before live use.")
if __name__=="__main__":main()
