#!/usr/bin/env python3
"""Shared read-only candle loading and exit simulation for Upbit listing backtests."""
import csv,zipfile,statistics
from collections import defaultdict
from datetime import datetime
def load(path):
 with zipfile.ZipFile(path) as z:
  eligible={r['market'] for r in csv.DictReader(z.read('universe.csv').decode().splitlines()) if r['status']=='complete'}
  bars=defaultdict(list)
  for r in csv.DictReader(z.read('candles_15m.csv').decode().splitlines()):
   if r['market'] not in eligible:continue
   bars[r['market']].append(dict(t=datetime.fromisoformat(r['t_utc'].replace('Z','+00:00')),
     o=float(r['open']),h=float(r['high']),l=float(r['low']),c=float(r['close']),v=float(r['value_krw'])))
 for values in bars.values():values.sort(key=lambda v:v['t'])
 return bars
def backtest(b,idx,mode):
 fee=.0005;slip=.0015
 entry=b[idx]['o']*(1+slip);entry_time=b[idx]['t'];stop=entry*.97
 target=entry*1.20 if mode=='fixed' else float('inf')
 highest=entry;reason='time';exit_idx=len(b)-1;price=b[-1]['c']*(1-slip)
 for k in range(idx,len(b)):
  x=b[k]
  if x['l']<=stop:
   price=stop*(1-slip);reason='stop';exit_idx=k;break
  if x['h']>=target:
   price=target*(1-slip);reason='take';exit_idx=k;break
  highest=max(highest,x['h'])
  if mode=='trail':stop=max(stop,highest*.90) # new stop valid only for next completed bar
 net=100*(price*(1-fee)/(entry*(1+fee))-1)
 return dict(net_pct=net,reason=reason,entry_time=entry_time.isoformat(),
  exit_time=b[exit_idx]['t'].isoformat(),entry_bar=idx,exit_bar=exit_idx)
