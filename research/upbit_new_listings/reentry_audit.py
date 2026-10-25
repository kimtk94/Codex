#!/usr/bin/env python3
"""Re-entry research runner. Requires exit_comparison.py beside this file and archived candle zip."""
import argparse,csv,statistics,json,math
from datetime import timedelta
from pathlib import Path
from exit_comparison import load,backtest
def signal(b,start,end):
 if start>=end-1:return None
 peak=b[start]['h'];active=False;low=0.;lastlow=0
 for i in range(start+1,end):
  x=b[i]
  if not active:
   if x['l']<=peak*.8:active=True;low=x['l'];lastlow=i
   peak=max(peak,x['h']);continue
  if x['l']<low:low=x['l'];lastlow=i
  if i-lastlow<4 or x['c']<low*1.03 or i<16:continue
  r=b[i-3:i+1];p=b[i-7:i-3]
  avg=lambda aa:statistics.mean((v['h']-v['l'])/max(v['c'],1e-12) for v in aa)
  if avg(r)>=.8*avg(p):continue
  if statistics.mean(v['v'] for v in r)>=.75*statistics.mean(v['v'] for v in p):continue
  w=b[i-15:i+1];vwap=sum(v['c']*v['v'] for v in w)/max(sum(v['v'] for v in w),1e-12)
  if x['c']<=vwap or min(v['l'] for v in r[2:])<=min(v['l'] for v in r[:2]):continue
  return i+1
 return None
def sim(b,cap,mode):
 out=[];cursor=0;deadline=b[0]['t']+timedelta(hours=24)
 while len(out)<cap and cursor<len(b)-1:
  max_idx=next((i for i,v in enumerate(b) if v['t']>deadline),len(b)-1)
  entry=signal(b,cursor,max_idx)
  if entry is None or b[entry]['t']>deadline:break
  r=backtest(b,entry,mode);r['attempt']=len(out)+1;out.append(r)
  if r['exit_bar']>=len(b)-2:break
  cursor=r['exit_bar']+1
 return out
def main():
 a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--out',required=True);args=a.parse_args()
 out=Path(args.out);out.mkdir(parents=True,exist_ok=True);rows=[];summary=[]
 for market,b in load(args.source).items():
  for mode in ('fixed','trail'):
   for cap in (1,2,3):
    for r in sim(b,cap,mode):rows.append({'market':market,'year':b[0]['t'].year,'mode':mode,'max_entries':cap,**r})
 fields=['market','year','mode','max_entries','attempt','net_pct','reason','entry_time','exit_time','entry_bar','exit_bar']
 with (out/'reentry_trades.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 for mode in ('fixed','trail'):
  for cap in (1,2,3):
   for period,years in [('train',{2023,2024,2025}),('explored_2026',{2026})]:
    rr=[r for r in rows if r['mode']==mode and r['max_entries']==cap and r['year'] in years]
    if not rr:continue
    bycoin={}
    for r in rr:bycoin.setdefault(r['market'],[]).append(r['net_pct'])
    net=[r['net_pct'] for r in rr]
    chained=[100*(math.prod(1+x/100 for x in v)-1) for v in bycoin.values()]
    summary.append(dict(mode=mode,max_entries=cap,period=period,coins=len(bycoin),trades=len(rr),
      extra_entries=len(rr)-len(bycoin),mean_trade_net_pct=round(statistics.mean(net),4),
      median_trade_net_pct=round(statistics.median(net),4),
      mean_coin_chained_net_pct=round(statistics.mean(chained),4),
      win_trades=sum(x>0 for x in net),stops=sum(r['reason']=='stop' for r in rr)))
 with (out/'reentry_summary.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=summary[0].keys());w.writeheader();w.writerows(summary)
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
