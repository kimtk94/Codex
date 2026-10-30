#!/usr/bin/env python3
"""Audit NYSE regular-session OHLC bars and optionally STAGE missing Alpaca SIP bars.

Safety: source inputs are read-only, staged additions are written elsewhere, no live
execution, no Drive writes, no silent quote/feed substitution. No fabricated bars.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import requests

UTC = dt.timezone.utc
NY = ZoneInfo('America/New_York')
SCHEMA = ['market','candle_time_utc','candle_time_kst','open','high','low','close','volume','quote_volume','timestamp_ms','unit_min']


def last_completed_session(now: dt.datetime | None = None) -> str:
    """Do not audit today's unfinished session, including the pre-open window."""
    now = (now or dt.datetime.now(UTC)).astimezone(UTC)
    cal = xcals.get_calendar('XNYS')
    ny_date = now.astimezone(NY).date()
    for days in range(0, 15):
        day = (ny_date - dt.timedelta(days=days)).isoformat()
        if not cal.is_session(day):
            continue
        if now >= cal.session_close(day).to_pydatetime() + dt.timedelta(minutes=15):
            return day
    raise RuntimeError('No recently completed NYSE session')


def expected_starts(calendar: xcals.ExchangeCalendar, first_session: str,
                    last_session: str, timeframe: str) -> pd.DatetimeIndex:
    sessions = calendar.sessions_in_range(first_session, last_session)
    if timeframe == '1d':
        return pd.DatetimeIndex([calendar.session_open(s) for s in sessions], tz='UTC')
    parts = [pd.date_range(calendar.session_open(s), calendar.session_close(s),
                           freq='15min', inclusive='left') for s in sessions]
    return parts[0].append(parts[1:]) if parts else pd.DatetimeIndex([], tz='UTC')


def read_bars(path: Path, timeframe: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
    else:
        df = pd.read_parquet(path)
    required = {'open','high','low','close','candle_time_utc'}
    absent = required.difference(df.columns)
    if absent:
        raise ValueError(f'{path.name}: missing columns {sorted(absent)}')
    df = df.copy()
    df['candle_time_utc'] = pd.to_datetime(df['candle_time_utc'],utc=True,errors='raise')
    # Daily Alpaca 1Day bars may be timestamped at midnight UTC; normalize by
    # the matching NY market session *date* (not a naïve 24h rolling floor).
    if timeframe == '1d':
        cal = xcals.get_calendar('XNYS')
        starts=[]
        for t in df['candle_time_utc']:
            nydate=t.tz_convert(NY).date().isoformat()
            # Source 1Day bars may use UTC midnight for their trading date.
            if t.hour == 0 and t.minute == 0:
                nydate=t.date().isoformat()
            if not cal.is_session(nydate):
                raise ValueError(f'Unexpected daily bar date {nydate}')
            starts.append(cal.session_open(nydate))
        df['_start']=pd.DatetimeIndex(starts)
    else:
        df['_start']=df['candle_time_utc']
    return df


def evaluate(df: pd.DataFrame, symbol: str, timeframe: str,
             as_of: str) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    cal = xcals.get_calendar('XNYS')
    if df.empty:
        raise ValueError(f'{symbol}/{timeframe}: cannot infer start from empty source')
    if as_of < str(df['_start'].min().date()):
        raise ValueError('as_of earlier than earliest observation')
    first = df['_start'].min().tz_convert(NY).date().isoformat()
    if timeframe == '1d':
        first = df['_start'].min().date().isoformat()
    if not cal.is_session(first):
        first = cal.date_to_session(first, direction='next').date().isoformat()
    expected = expected_starts(cal,first,as_of,timeframe)
    observed = pd.DatetimeIndex(df.loc[df['_start']<=cal.session_close(as_of),'_start'])
    dup = int(observed.duplicated().sum())
    o = pd.to_numeric(df['open'],errors='coerce')
    h = pd.to_numeric(df['high'],errors='coerce')
    l = pd.to_numeric(df['low'],errors='coerce')
    c = pd.to_numeric(df['close'],errors='coerce')
    bad = int(((h<l)|(h<o)|(h<c)|(l>o)|(l>c)|(l<=0)|
               (o<=0)|(c<=0)|o.isna()|h.isna()|l.isna()|c.isna()).sum())
    off_session = int((~observed.isin(expected)).sum())
    missing = expected.difference(observed)
    missing_df = pd.DataFrame({'symbol':symbol,'timeframe':timeframe,
                               'start_utc':[t.isoformat() for t in missing]})
    missing_df['ny_date'] = pd.to_datetime(missing_df['start_utc'],utc=True).dt.tz_convert(NY).dt.strftime('%Y-%m-%d')
    report = dict(symbol=symbol,timeframe=timeframe,source_rows=len(df),
                  source_first=df['_start'].min().isoformat(),
                  source_last=df['_start'].max().isoformat(),as_of=as_of,
                  expected=len(expected),observed_unique=len(observed.unique()),
                  missing=len(missing),duplicates=dup,bad_ohlc=bad,
                  off_session=off_session,
                  coverage_pct=round(100*(len(expected)-len(missing))/max(1,len(expected)),6))
    return missing_df, report, df


def _fetch_month(session:requests.Session,symbol:str,timeframe:str,
                 first_utc:pd.Timestamp,last_utc:pd.Timestamp,
                 timeout:int=35, sleep:Callable[[float],None]=time.sleep) -> list[dict]:
    if not os.environ.get('ALPACA_API_KEY_ID') or not os.environ.get('ALPACA_API_SECRET_KEY'):
        raise RuntimeError('BLOCKED: ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY required')
    params={'timeframe':'15Min' if timeframe=='15m' else '1Day',
            'start':first_utc.isoformat().replace('+00:00','Z'),
            'end':last_utc.isoformat().replace('+00:00','Z'),
            'limit':10000,'sort':'asc','feed':'sip','adjustment':'all'}
    headers={'APCA-API-KEY-ID':os.environ['ALPACA_API_KEY_ID'],
             'APCA-API-SECRET-KEY':os.environ['ALPACA_API_SECRET_KEY']}
    all_bars=[]; next_token=None; visited=set()
    while True:
        q=dict(params)
        if next_token: q['page_token']=next_token
        response=None
        for retry in range(6):
            response=session.get(f'https://data.alpaca.markets/v2/stocks/{symbol}/bars',
                                 params=q,headers=headers,timeout=timeout)
            if response.status_code in (429,500,502,503,504):
                sleep(min(30,2**retry));continue
            response.raise_for_status();break
        else:raise RuntimeError(f'Alpaca API retries exhausted: {response.status_code}')
        payload=response.json()
        batch=payload.get('bars')
        if not isinstance(batch,list):raise ValueError('Malformed Alpaca bars response')
        all_bars.extend(batch)
        next_token=payload.get('next_page_token')
        if not next_token:break
        if next_token in visited:raise RuntimeError('Repeated pagination token')
        visited.add(next_token)
        sleep(.1)
    return all_bars


def staged_dataframe(symbol:str,timeframe:str,bars:list[dict],needed:set[str],
                     cal:xcals.ExchangeCalendar) -> pd.DataFrame:
    unit=15 if timeframe=='15m' else 1440
    out=[]
    for b in bars:
        t=pd.Timestamp(b['t']).tz_convert('UTC')
        if timeframe=='1d':
            # Official Alpaca daily timestamp is UTC midnight trading date.
            day=t.date().isoformat() if t.hour==0 else t.tz_convert(NY).date().isoformat()
            if not cal.is_session(day):continue
            start=cal.session_open(day)
        else:start=t
        if start.isoformat() not in needed:continue
        op,hi,lo,cl=[float(b[k]) for k in ('o','h','l','c')]
        if not (hi>=max(op,cl)>=min(op,cl)>=lo>0):
            raise ValueError(f'Invalid returned OHLC: {symbol} {start}')
        volume=float(b.get('v',0))
        if volume < 0:raise ValueError('Negative volume')
        # Alpaca VWAP * volume is an estimate, not independently measured dollar volume.
        quote_volume=volume*float(b.get('vw',cl))
        out.append(dict(market=symbol,candle_time_utc=start,
                        candle_time_kst=start.tz_convert('Asia/Seoul'),
                        open=op,high=hi,low=lo,close=cl,
                        volume=volume,quote_volume=quote_volume,
                        timestamp_ms=int(start.timestamp()*1000),unit_min=unit))
    return pd.DataFrame(out,columns=SCHEMA)


def stage_missing(symbol:str,timeframe:str,missing_df:pd.DataFrame,
                  session:requests.Session,cal:xcals.ExchangeCalendar,
                  max_months:int=24) -> tuple[pd.DataFrame,dict]:
    if missing_df.empty:return pd.DataFrame(columns=SCHEMA),{'months':0,'downloaded_rows':0}
    missing = pd.to_datetime(missing_df['start_utc'],utc=True)
    months = sorted(set((t.year,t.month) for t in missing))
    if len(months)>max_months:
        raise RuntimeError(f'BLOCKED: {len(months)} missing months exceeds --max-months {max_months}')
    results=[]; seen_downloaded=0
    missing_set=set(missing_df['start_utc'])
    for year,month in months:
        start=pd.Timestamp(dt.datetime(year,month,1,tzinfo=UTC))-pd.Timedelta(days=2)
        nextmo=pd.Timestamp(dt.datetime(year+int(month==12),month%12+1,1,tzinfo=UTC)) + pd.Timedelta(days=2)
        bars=_fetch_month(session,symbol,timeframe,start,nextmo)
        seen_downloaded+=len(bars)
        frame=staged_dataframe(symbol,timeframe,bars,missing_set,cal)
        if not frame.empty:results.append(frame)
    merged=pd.concat(results,ignore_index=True) if results else pd.DataFrame(columns=SCHEMA)
    if not merged.empty:
        merged=merged.drop_duplicates(subset=['market','candle_time_utc','unit_min'])
    return merged,{'months':len(months),'downloaded_rows':seen_downloaded}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',action='append',required=True,
                   help='SYMBOL:15m:/path/file.parquet or SYMBOL:1d:/path/file.parquet')
    p.add_argument('--as-of',default=None,help='Last completed NYSE date (YYYY-MM-DD), default auto')
    p.add_argument('--out-dir',default='outputs/kalman_gap_audit')
    p.add_argument('--fetch',action='store_true',help='Read Alpaca SIP and stage additions; never merge source')
    p.add_argument('--max-months',type=int,default=24)
    args=p.parse_args(argv)
    as_of=args.as_of or last_completed_session()
    cal=xcals.get_calendar('XNYS')
    if not cal.is_session(as_of):p.error('--as-of must be an NYSE session')
    last_actual=last_completed_session()
    if as_of>last_actual:p.error('--as-of cannot exceed last completed NYSE session')
    out=Path(args.out_dir)
    out.mkdir(parents=True,exist_ok=True)
    all_gaps=[];reports=[];stages=[]
    for setting in args.dataset:
        parts=setting.split(':',2)
        if len(parts)!=3 or parts[1] not in ('15m','1d'):
            p.error(f'Invalid --dataset {setting}')
        symbol,timeframe,filename=parts
        if not (symbol.isascii() and symbol.isalpha() and symbol.isupper()):
            p.error('Symbol must be simple uppercase ticker')
        data=read_bars(Path(filename),timeframe)
        missing,report,_=evaluate(data,symbol,timeframe,as_of)
        all_gaps.append(missing)
        if args.fetch:
            with requests.Session() as s:
                additions,download=stage_missing(symbol,timeframe,missing,s,cal,args.max_months)
            report.update(download)
            report['staged_additions']=len(additions)
            report['remaining_missing']=len(missing)-len(additions)
            if not additions.empty:stages.append(additions)
        reports.append(report)
        print(json.dumps(report,ensure_ascii=False),flush=True)
    gaps=pd.concat(all_gaps,ignore_index=True)
    gaps.to_csv(out/'missing_bars.csv',index=False)
    summary={'status':'STAGED' if args.fetch else 'AUDIT_ONLY',
             'as_of':as_of,'source_mutated':False,'live_policy_modified':False,
             'provenance':'Alpaca SIP adjusted=all, NYSE regular hours',
             'datasets':reports}
    if args.fetch:
        combined=pd.concat(stages,ignore_index=True) if stages else pd.DataFrame(columns=SCHEMA)
        if not combined.empty:
            combined.to_parquet(out/'proposed_additions.parquet',index=False)
        staged_keys=set()
        if not combined.empty:
            staged_keys=set(zip(combined['market'],combined['unit_min'],combined['candle_time_utc'].dt.strftime('%Y-%m-%dT%H:%M:%S%z')))
        unfilled=[]
        for row in gaps.itertuples(index=False):
            stamp=pd.Timestamp(row.start_utc).strftime('%Y-%m-%dT%H:%M:%S%z')
            if (row.symbol,15 if row.timeframe=='15m' else 1440,stamp) not in staged_keys:
                unfilled.append(row._asdict())
        pd.DataFrame(unfilled,columns=['symbol','timeframe','start_utc','ny_date']).to_csv(out/'unfilled_gaps.csv',index=False)
        summary['stage_rows']=len(combined)
        summary['unfilled_rows']=len(unfilled)
        summary['status']='STAGED_COMPLETE' if not unfilled else 'STAGED_PARTIAL'
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    return 0 if all(x['bad_ohlc']==0 and x['duplicates']==0 for x in reports) else 2


if __name__=='__main__':sys.exit(main())
