#!/usr/bin/env python3
"""Read-only, research-only FX provider triangulation; never emits market prices.

Analyzes a private Kalman ZIP locally (within GitHub Actions). The comparison
sources are 1) Yahoo KRW=X with repair True/False, 2) optionally Stooq USDKRW OHLC,
3) ECB reference via Frankfurter (mid/reference prices, not comparable FX daily bar OHLC).
Never fills source bars, never de-quarantines tainted research features automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
from datetime import date, datetime, timezone
import re

import numpy as np
import pandas as pd

SOURCE = 'market/raw/yfinance/yf_usdkrw.parquet'
FRED = 'fred/fred_latest_revised_long.csv'
EXPECTED_YAHOO_TICKER = 'KRW=X'


def validate_bar(row):
    """Return (is_valid, violation_bps); do not silently round borderline violations."""
    try:
        o,h,l,c = (float(row[k]) for k in ('open','high','low','close'))
    except (ValueError, TypeError, KeyError):
        return False, None
    if not np.isfinite([o,h,l,c]).all() or min(o,h,l,c)<=0:
        return False, None
    excess = max(0.,l-h,o-h,c-h,l-o,l-c)
    return excess <= 1e-8, round(10000*excess/abs(c),5)


def verified_zip_frame(path):
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('manifest.json'))
        meta={r['path']:r['sha256'] for r in manifest['members']}
        for name in (SOURCE,FRED):
            if name not in meta or hashlib.sha256(z.read(name)).hexdigest()!=meta[name]:
                raise ValueError('MANIFEST_SHA_MISMATCH_'+name)
        if manifest.get('status')!='RESEARCH_ONLY_VALIDATED':
            raise ValueError('UNVERIFIED_RESEARCH_ZIP')
        frame=pd.read_parquet(io.BytesIO(z.read(SOURCE)))
        status=json.loads(z.read('readiness.json'))
        if status.get('research_only') is not True or status.get('production_writes') is not False:
            raise ValueError('BAD_RESEARCH_SCOPE')
    dates=pd.to_datetime(frame['timestamp'],errors='raise',utc=True).dt.strftime('%Y-%m-%d')
    frame=frame.assign(date=dates).set_index('date',drop=False)
    if frame.index.duplicated().any(): raise ValueError('DUPLICATE_SOURCE_DATES')
    if (frame['symbol'].astype(str)!= 'USD/KRW').any():
        raise ValueError('SOURCE_PAIR_MISMATCH')
    return frame,status


def flatten_yahoo(data, ticker):
    if isinstance(data.columns,pd.MultiIndex):
        for level in range(data.columns.nlevels):
            if ticker in data.columns.get_level_values(level):
                data=data.xs(ticker,axis=1,level=level)
                break
    if isinstance(data.columns,pd.MultiIndex):
        raise ValueError('AMBIGUOUS_YAHOO_COLUMNS')
    frame=data.rename(columns=lambda c: str(c).strip().lower().replace(' ','_')).copy()
    if not {'open','high','low','close'}.issubset(frame.columns):
        raise ValueError('YAHOO_MISSING_OHLC')
    frame.index=pd.to_datetime(frame.index,utc=True)
    frame['date']=frame.index.strftime('%Y-%m-%d')
    if frame['date'].duplicated().any():raise ValueError('YAHOO_DUPLICATE_DATES')
    return frame.set_index('date')


def load_yahoo(ticker,first,last,repair):
    import yfinance as yf
    # All days, including a buffer to avoid end-date exclusive behavior.
    end=(pd.Timestamp(last)+pd.Timedelta(days=2)).strftime('%Y-%m-%d')
    out=yf.download(ticker,start=first,end=end,interval='1d',auto_adjust=False,
        repair=repair,keepna=True,ignore_tz=True,progress=False,
        group_by='column',threads=False,timeout=25)
    if out is None or out.empty:raise RuntimeError('NO_YAHOO_BARS')
    return flatten_yahoo(out,ticker)


def load_stooq(first,last):
    import requests
    params={'s':'usdkrw','i':'d','d1':first.replace('-',''),'d2':last.replace('-','')}
    r=requests.get('https://stooq.com/q/d/l/',params=params,timeout=(8,20),
                   headers={'User-Agent':'Kalman-Research-FX-Check/1.0'})
    r.raise_for_status()
    if 'date,open,high,low,close' not in r.text[:150].lower():
        raise ValueError('STOOQ_NOT_CSV_OR_ACCESS_RESTRICTED')
    data=pd.read_csv(io.StringIO(r.text)).rename(columns=lambda x:str(x).lower())
    if not {'date','open','high','low','close'}.issubset(data.columns):
        raise ValueError('STOOQ_SCHEMA_MISMATCH')
    if len(data)<20:raise ValueError('STOOQ_TOO_FEW_BARS')
    dates=pd.to_datetime(data['date'],format='%Y-%m-%d',errors='raise')
    data=data.assign(date=dates.dt.strftime('%Y-%m-%d'))
    if data['date'].duplicated().any():raise ValueError('STOOQ_DUPLICATE_DATES')
    return data.set_index('date')


def load_ecb_reference(first,last):
    import requests
    # Frankfurter is an API proxy to ECB; reference values are NOT FX 24h OHLC.
    params={'from':first,'to':last,'base':'USD','quotes':'KRW'}
    r=requests.get('https://api.frankfurter.dev/v2/providers/ecb/rates',params=params,
                   timeout=(8,25),headers={'User-Agent':'Kalman-Research-FX-Check/1.0'})
    r.raise_for_status()
    payload=r.json()
    if not isinstance(payload,list):raise ValueError('ECB_RESPONSE_NOT_LIST')
    out={}
    for row in payload:
        if row.get('quote','').upper()!='KRW' or row.get('base','').upper()!='USD':
            continue
        dt=row.get('date');rate=row.get('rate')
        try:price=float(rate)
        except (TypeError,ValueError):continue
        if isinstance(dt,str) and np.isfinite(price) and price>0:
            out[dt]=price
    if len(out)<20:raise ValueError('ECB_TOO_FEW_DAILY_REFERENCES')
    return out


def label_audit(source_valid,repair_valid,raw_valid,stooq_valid):
    """Candidate root cause only; independent provider must never auto-repair."""
    if source_valid: return 'SOURCE_NOW_VALID'
    if raw_valid is True and repair_valid is False:
        return 'YAHOO_REPAIR_FLAG_CANDIDATE'
    if raw_valid is False and repair_valid is False:
        return 'YAHOO_UNREPAIRED_AND_REPAIRED_INVALID'
    if raw_valid is True and repair_valid is True:
        return 'SNAPSHOT_OR_UPSTREAM_VERSION_DRIFT'
    if raw_valid is False and repair_valid is True:
        return 'REPAIR_MAY_HAVE_CORRECTED_NEW_DOWNLOAD'
    return 'INSUFFICIENT_PROVIDER_EVIDENCE'


def status_for(df,date):
    if df is None:return None,None
    if date not in df.index:return None,None
    return validate_bar(df.loc[date])


def produce(source_zip,out_dir,*,expected_sha256=None):
    source_zip=Path(source_zip)
    input_sha256=hashlib.sha256(source_zip.read_bytes()).hexdigest()
    if expected_sha256 is not None and (
        not re.fullmatch(r'[a-f0-9]{64}',expected_sha256) or input_sha256!=expected_sha256
    ):
        raise ValueError('FX_INPUT_SHA256_MISMATCH')
    original,readiness=verified_zip_frame(source_zip)
    asof=readiness.get('expected_last_completed_nyse_session')
    if not isinstance(asof,str) or date.fromisoformat(asof).isoformat()!=asof:
        raise ValueError('FX_INVALID_COMMON_ASOF')
    after_asof=sorted(str(d) for d in original.index if d>asof)
    eligible=original.loc[original.index<=asof]
    if eligible.empty:raise ValueError('FX_NO_OBSERVATIONS_AT_OR_BEFORE_COMMON_ASOF')
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    flagged=[]
    for d,row in eligible.iterrows():
        good,bps=validate_bar(row)
        if not good:flagged.append((d,bps))
    first=min(eligible.index);last=max(eligible.index)
    feeds={};availability={}
    for name,getter in (
        ('yahoo_repair_true',lambda:load_yahoo(EXPECTED_YAHOO_TICKER,first,last,True)),
        ('yahoo_repair_false',lambda:load_yahoo(EXPECTED_YAHOO_TICKER,first,last,False)),
        ('stooq_independent_ohlc',lambda:load_stooq(first,last)),
        ('ecb_reference',lambda:load_ecb_reference(first,last)),
    ):
        if not flagged:
            feeds[name]=None;availability[name]='NOT_NEEDED_NO_FLAGGED_BARS'
            continue
        try:
            feeds[name]=getter();availability[name]='AVAILABLE'
        except Exception as ex:
            feeds[name]=None
            availability[name]='UNAVAILABLE_'+type(ex).__name__
    rows=[]
    for day,excess in flagged:
        yrepair,br=status_for(feeds['yahoo_repair_true'],day)
        ynorepair,bnr=status_for(feeds['yahoo_repair_false'],day)
        stooq,bs=status_for(feeds['stooq_independent_ohlc'],day)
        ecb=feeds['ecb_reference']
        ecb_available=bool(ecb and day in ecb)
        # Reference context only; do not compare to a daily candlestick close in a way that suggests replacement.
        rows.append({'date':day,'source_excess_bp':excess,
            'yahoo_repair_bar_valid':yrepair,'yahoo_unrepaired_bar_valid':ynorepair,
            'stooq_bar_valid':stooq,'ecb_reference_available':ecb_available,
            'source_issue_classification':label_audit(False,yrepair,ynorepair,stooq),
            'independent_ohlc_confirmed_valid':stooq is True,
            'original_source_same_session_ohlc_certified':False,
            'automated_repair_approved':False,
            'training_eligible':False})
    result=pd.DataFrame(rows,columns=[
        'date','source_excess_bp','yahoo_repair_bar_valid','yahoo_unrepaired_bar_valid',
        'stooq_bar_valid','ecb_reference_available','source_issue_classification',
        'independent_ohlc_confirmed_valid','original_source_same_session_ohlc_certified',
        'automated_repair_approved','training_eligible'])
    result.to_csv(out_dir/'fx_source_triangulation.csv',index=False)
    status={'schema':'kalman-fx-triangulation-v1','generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'input_sha256':input_sha256,
        'input_sha256_pinned':expected_sha256 is not None,
        'common_completed_xnys_asof':asof,
        'source_rows_at_or_before_common_asof':len(eligible),
        'source_rows_after_common_asof':len(after_asof),
        'source_dates_after_common_asof':after_asof,
        'original_source_same_session_ohlc_certified_dates':0,
        'usdkrw_provider_symbol':EXPECTED_YAHOO_TICKER,
        'anomaly_dates':len(rows),'provider_status':availability,
        'classifications':result['source_issue_classification'].value_counts().to_dict(),
        'stooq_ohlc_valid_for_flagged':int(result['stooq_bar_valid'].eq(True).sum()),
        'ecb_reference_days_covered':int(result['ecb_reference_available'].sum()),
        'auto_corrected_ohlc':0,'excluded_from_training':len(rows),
        'source_rewritten':False,'live_state_written':False,
        'limitation':'Stooq validity means its own OHLC is internally valid, not certification of the original session bar. ECB is a daily reference only. Common XNYS as-of is not FX-session finality. No auto-replacement. FRED latest-revised is not PIT vintage.'}
    (out_dir/'fx_source_triangulation_summary.json').write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
    # Strict research gate remains conservative regardless of external evidence.
    mask={'schema':'kalman-fx-research-gate-v1','ohlc_replacement_approved':False,
          'affected_dates':sorted(result['date'].to_list()),
          'excluded_after_common_asof_dates':after_asof,
          'ta_lib_fx_features_training_eligible':False,
          'historical_fred_vintage_training_eligible':False,'live_policy_modified':False}
    (out_dir/'fx_research_gate.json').write_text(json.dumps(mask,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(status,ensure_ascii=False))
    return status


def main():
    p=argparse.ArgumentParser();p.add_argument('--zip',required=True);p.add_argument('--out',required=True)
    p.add_argument('--expected-sha256')
    a=p.parse_args();produce(a.zip,a.out,expected_sha256=a.expected_sha256)

if __name__=='__main__':main()