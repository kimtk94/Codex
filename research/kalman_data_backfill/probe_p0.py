#!/usr/bin/env python3
"""Sample P0 instrument access and temporal coverage. NEVER save licensed raw bars.

Checks 7 US stock/ETF symbols with Alpaca SIP on the latest completed XNYS
sessions, and 2 KRW pairs via Upbit public OHLC metadata. Research only.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
import pandas as pd
import requests
import exchange_calendars as xcals
from audit_stage import last_completed_session, expected_starts

US_15M=('QQQ','QLD','SPY','SMH','NVDA','TSLA','AMD')
US_1M=('QQQ','QLD','NVDA','TSLA','AMD')
UPBIT=('KRW-BTC','KRW-ETH')
API='https://data.alpaca.markets/v2/stocks'
UPBIT_API='https://api.upbit.com/v1/candles/minutes'

def request_json(s:requests.Session,url:str,params:dict,headers:dict|None=None):
    for attempt in range(5):
        response=s.get(url,params=params,headers=headers,timeout=35)
        if response.status_code in (429,500,502,503,504):
            time.sleep(min(15,2**attempt))
            continue
        if response.status_code in (401,403,422):
            return None, 'PROVIDER_ACCESS_DENIED_'+str(response.status_code)
        response.raise_for_status()
        return response.json(),None
    return None,'PROVIDER_RETRY_EXHAUSTED'

def probe_us(s:requests.Session,symbol:str,timeframe:str,cal,as_of:str,key:str,secret:str,session_count:int):
    sessions=cal.sessions_in_range('2026-01-01',as_of)
    if len(sessions)<session_count: raise ValueError('Insufficient sessions')
    first=sessions[-session_count].date().isoformat()
    starts=expected_starts(cal,first,as_of,'15m') if timeframe=='15m' else pd.DatetimeIndex(
        [t for day in sessions[-session_count:] for t in pd.date_range(
          cal.session_open(day),cal.session_close(day),freq='1min',inclusive='left')],tz='UTC')
    expected=set(starts)
    params=dict(timeframe='15Min' if timeframe=='15m' else '1Min',
                start=cal.session_open(first).isoformat(),
                end=cal.session_close(as_of).isoformat(),
                feed='sip',adjustment='all',limit=10000,sort='asc')
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    observed=set(); pages=0; tokens=set()
    while True:
        payload,err=request_json(s,f'{API}/{symbol}/bars',params,headers)
        if err:return dict(symbol=symbol,market='US',timeframe=timeframe,status=err,expected=len(expected),observed=len(observed))
        if not isinstance(payload,dict) or not isinstance(payload.get('bars'),list):
            return dict(symbol=symbol,market='US',timeframe=timeframe,status='PROVIDER_RESPONSE_INVALID')
        for b in payload['bars']:
            t=pd.Timestamp(b['t']).tz_convert('UTC')
            if t in expected:observed.add(t)
        pages+=1
        token=payload.get('next_page_token')
        if not token:break
        if token in tokens or pages>1000:raise ValueError('Alpaca pagination loop')
        tokens.add(token);params['page_token']=token
        time.sleep(.12)
    missing=expected-observed
    return dict(symbol=symbol,market='US',timeframe=timeframe,status='COVERAGE_GAPS' if missing else 'SAMPLE_OK',
                session_count=session_count,start_ny=first,end_ny=as_of,
                expected=len(expected),observed=len(observed),missing=len(missing),pages=pages,feed='sip',
                missing_first_utc=min(missing).isoformat() if missing else None)

def probe_upbit(s:requests.Session,market:str,unit:int):
    payload,err=request_json(s,f'{UPBIT_API}/{unit}',dict(market=market,count=200),
                             headers={'Accept':'application/json','User-Agent':'kalman-research-audit/1.0'})
    if err:return dict(symbol=market,market='UPBIT',timeframe=f'{unit}m',status=err)
    if not isinstance(payload,list) or not payload:
        return dict(symbol=market,market='UPBIT',timeframe=f'{unit}m',status='EMPTY_OR_MALFORMED')
    times=sorted(set(pd.Timestamp(x['candle_date_time_utc']).tz_localize('UTC') for x in payload))
    return dict(symbol=market,market='UPBIT',timeframe=f'{unit}m',status='SAMPLE_OK',
                observed=len(times),requested_count=200,first_utc=times[0].isoformat(),
                last_utc=times[-1].isoformat(),
                note='Upbit omits intervals without trades: elapsed-time gaps alone are NOT data defects')

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--as-of',default=None)
    ap.add_argument('--out',default='outputs/p0_readiness.json')
    args=ap.parse_args(argv)
    as_of=args.as_of or last_completed_session()
    cal=xcals.get_calendar('XNYS')
    if not cal.is_session(as_of):ap.error('Invalid NYSE trading session')
    key=os.environ.get('ALPACA_API_KEY_ID','')
    secret=os.environ.get('ALPACA_API_SECRET_KEY','')
    rows=[]
    with requests.Session() as s:
        for symbol in US_15M:
            if not key or not secret:
                rows.append(dict(symbol=symbol,market='US',timeframe='15m',status='BLOCKED_MISSING_ALPACA_SECRET'))
            else:
                try:rows.append(probe_us(s,symbol,'15m',cal,as_of,key,secret,20))
                except Exception as e:rows.append(dict(symbol=symbol,market='US',timeframe='15m',status='ERROR',error_type=type(e).__name__))
        for symbol in US_1M:
            if not key or not secret:
                rows.append(dict(symbol=symbol,market='US',timeframe='1m',status='BLOCKED_MISSING_ALPACA_SECRET'))
            else:
                try:rows.append(probe_us(s,symbol,'1m',cal,as_of,key,secret,1))
                except Exception as e:rows.append(dict(symbol=symbol,market='US',timeframe='1m',status='ERROR',error_type=type(e).__name__))
        for symbol in UPBIT:
            for unit in (1,15):
                try:rows.append(probe_upbit(s,symbol,unit))
                except Exception as e:rows.append(dict(symbol=symbol,market='UPBIT',timeframe=f'{unit}m',status='ERROR',error_type=type(e).__name__))
    # Missing bars in sampled interval are metadata, not an authorization to fill or to trade.
    status='BLOCKED' if any(r['status'].startswith(('BLOCKED','PROVIDER_ACCESS_DENIED','PROVIDER_RETRY','ERROR')) for r in rows) else (
        'PARTIAL' if any(r['status']!='SAMPLE_OK' for r in rows) else 'SAMPLE_OK')
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    result=dict(status=status,as_of=as_of,run_type='PROVIDER_METADATA_ONLY',feed='Alpaca SIP, Upbit',
                no_raw_prices_saved=True,live_policy_modified=False,items=rows)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=status,as_of=as_of,results_count=len(rows),
                          blocked=sum(r['status'].startswith(('BLOCKED','PROVIDER_ACCESS_DENIED')) for r in rows),
                          incomplete=sum(r['status']!='SAMPLE_OK' for r in rows)),ensure_ascii=False))
    return 0 if status in ('SAMPLE_OK','PARTIAL') else 2

if __name__=='__main__':
    raise SystemExit(main())
