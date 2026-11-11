#!/usr/bin/env python3
"""Read-only Upbit KRW-BTC/ETH raw backfill, staged as gzipped monthly CSV.

No trades, no credentials, no overwriting existing Drive data. Upbit candles
do not exist for minutes with zero trades; gaps are never silently invented.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import gzip
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
KST=ZoneInfo('Asia/Seoul')
DEFAULT_MARKETS=['KRW-BTC','KRW-ETH']
FIELDS=['market','unit_min','time_utc','time_kst','open','high','low','close','volume','quote_volume']
URL='https://api.upbit.com/v1/candles/minutes/'

def as_utc(x:str)->dt.datetime:
    return dt.datetime.fromisoformat(x.replace('Z','+00:00')).astimezone(UTC)

def request_batch(market:str,unit:int,cursor:dt.datetime,opener=urllib.request.urlopen,sleeper=time.sleep):
    params=urllib.parse.urlencode({'market':market,'count':200,'to':cursor.strftime('%Y-%m-%dT%H:%M:%SZ')})
    url=f'{URL}{unit}?{params}'
    for retry in range(7):
        try:
            req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'kalman-upbit-history-research/1.0'})
            with opener(req,timeout=35) as stream:data=json.load(stream)
            if not isinstance(data,list):raise ValueError('Upbit non-list response')
            return data
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError) as exc:
            if isinstance(exc,urllib.error.HTTPError) and exc.code not in (429,500,502,503,504):raise
            if retry==6:raise
            sleeper(min(25,2**retry)+random.uniform(0,.3))
    raise RuntimeError('Retry loop exhausted')

def normalize(b:dict,market:str,unit:int)->dict:
    t=dt.datetime.fromisoformat(b['candle_date_time_utc']).replace(tzinfo=UTC)
    values=[float(b[k]) for k in ('opening_price','high_price','low_price','trade_price')]
    o,h,l,c=values
    if not (h>=max(o,c)>=min(o,c)>=l>0):raise ValueError(f'BAD_OHLC {market} {t}')
    vol=float(b['candle_acc_trade_volume'])
    quote=float(b['candle_acc_trade_price'])
    if vol<0 or quote<0:raise ValueError(f'BAD_VOLUME {market} {t}')
    return dict(market=market,unit_min=unit,time_utc=t.isoformat(),
                time_kst=t.astimezone(KST).isoformat(),open=o,high=h,low=l,close=c,
                volume=vol,quote_volume=quote)

def collect(market:str,unit:int,start:dt.datetime,end:dt.datetime,
            max_pages:int=2500,fetch=request_batch,sleeper=time.sleep):
    cursor=end
    rows={}
    pages=0
    oldest_seen=None
    while cursor>start:
        data=fetch(market,unit,cursor)
        if not data:
            raise RuntimeError('Upbit returned zero candles before start reached; no complete claim')
        stamps=[dt.datetime.fromisoformat(b['candle_date_time_utc']).replace(tzinfo=UTC) for b in data]
        oldest=min(stamps)
        if oldest>=cursor:raise RuntimeError('Cursor did not move backward')
        if oldest_seen is not None and oldest>=oldest_seen:raise RuntimeError('Non-decreasing oldest seen')
        oldest_seen=oldest
        for bar,t in zip(data,stamps):
            if start<=t<end:rows[t.isoformat()]=normalize(bar,market,unit)
        pages+=1
        if pages%100==0:
            print(json.dumps({'market':market,'unit':unit,'pages':pages,
                              'rows':len(rows),'cursor':oldest.isoformat()}),flush=True)
        cursor=oldest
        if pages>=max_pages and cursor>start:
            raise RuntimeError(f'PAGE_CAP_HIT_{max_pages}: source coverage incomplete; abort outputs')
        sleeper(.18)
    return [rows[k] for k in sorted(rows)],pages

def write_monthly(outdir:Path,market:str,unit:int,rows:list[dict])->list[str]:
    bins=defaultdict(list)
    for r in rows:
        month=r['time_kst'][:7]
        bins[month].append(r)
    paths=[]
    for month,values in sorted(bins.items()):
        folder=outdir/month[:4]
        folder.mkdir(parents=True,exist_ok=True)
        name=f'{market.replace("-","_")}_{unit}m_raw_{month.replace("-","_")}.csv.gz'
        path=folder/name
        with gzip.open(path,'wt',encoding='utf-8',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(values)
        paths.append(str(path.relative_to(outdir)))
    return paths

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--start',default='2026-08-16T00:00:00Z')
    p.add_argument('--end',default=None)
    p.add_argument('--markets',default='KRW-BTC,KRW-ETH')
    p.add_argument('--units',default='1,15')
    p.add_argument('--out-dir',default='outputs/upbit_raw_backfill')
    p.add_argument('--max-pages',type=int,default=2500)
    a=p.parse_args(argv)
    start=as_utc(a.start)
    now=dt.datetime.now(UTC)
    end=as_utc(a.end) if a.end else now.replace(second=0,microsecond=0)
    if start>=end or end>now:raise ValueError('Require valid nonfuture start < end')
    markets=[s.strip().upper() for s in a.markets.split(',') if s.strip()]
    units=[int(s) for s in a.units.split(',')]
    if any(m not in DEFAULT_MARKETS for m in markets) or any(u not in (1,15) for u in units):
        raise ValueError('Only approved KRW-BTC,KRW-ETH and 1,15 minute research periods')
    outdir=Path(a.out_dir)
    stats=[]
    for market in markets:
        for unit in units:
            bars,pages=collect(market,unit,start,end,a.max_pages)
            paths=write_monthly(outdir,market,unit,bars)
            stats.append({'market':market,'unit_min':unit,'pages':pages,'count':len(bars),
                          'first_utc':bars[0]['time_utc'] if bars else None,
                          'last_utc':bars[-1]['time_utc'] if bars else None,
                          'files':paths,'status':'BACKFILL_STAGED'})
            print(json.dumps({'market':market,'unit':unit,'rows':len(bars),'pages':pages,
                              'files':len(paths)},flush=True))
    report={'status':'STAGED_NOT_MERGED','source':'Upbit public REST',
            'start_utc':start.isoformat(),'end_exclusive_utc':end.isoformat(),
            'no_trade_minutes_are_not_imputed':True,'no_live_orders':True,
            'existing_drive_modified':False,'datasets':stats}
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'datasets':len(stats),
                      'rows_total':sum(x['count'] for x in stats)}))
    return 0

if __name__=='__main__':raise SystemExit(main())
