#!/usr/bin/env python3
"""Immutable QQQ/QLD staged-vs-source audit and bounded old-gap SIP recovery.

All source + stage files are read-only. Writes only new research evidence under --out.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import requests
import pandas as pd
import exchange_calendars as xcals
from audit_stage import read_bars, evaluate, stage_missing, staged_dataframe, _fetch_month

UTC = 'UTC'
CUT = pd.Timestamp('2026-09-01T00:00:00Z')
BASE = ('QQQ', 'QLD')
FRAMES = ('15m','1d')


def digest(path):
    with open(path, 'rb') as f:
        h=hashlib.sha256()
        for c in iter(lambda:f.read(1024*1024),b''):
            h.update(c)
    return h.hexdigest()


def validate_one(srcpath:Path, stagedpaths:list[Path],symbol:str,frame:str,as_of:str,
                 session:requests.Session, calendar, out:Path, recover_old:bool):
    hashes={str(p.name):digest(p) for p in [srcpath,*stagedpaths]}
    source=read_bars(srcpath,frame)
    missing, report, _=evaluate(source,symbol,frame,as_of)
    source_starts=pd.DatetimeIndex(source['_start'])
    stages=[read_bars(p,frame) for p in stagedpaths]
    staged=pd.concat(stages,ignore_index=True)
    staged_starts=pd.DatetimeIndex(staged['_start'])
    missing_ts=pd.DatetimeIndex(pd.to_datetime(missing['start_utc'],utc=True))
    expected_recent=missing_ts[missing_ts>=CUT]
    expected_old=missing_ts[missing_ts<CUT]
    duplicate=int(staged_starts.duplicated().sum())
    overlap=int(staged_starts.isin(source_starts).sum())
    unexpected=int((~staged_starts.isin(expected_recent)).sum())
    not_collected=expected_recent.difference(staged_starts)
    staged_bad=int(((staged['high']<staged['low']) |
        (staged['high']<staged[['open','close']].max(axis=1)) |
        (staged['low']>staged[['open','close']].min(axis=1)) |
        (staged[['open','high','low','close']]<=0).any(axis=1) |
        staged[['open','high','low','close']].isna().any(axis=1)).sum())
    stages_valid=not (duplicate or overlap or unexpected or len(not_collected) or staged_bad)
    # Compare ORIGINAL raw prices to freshly fetched SIP-adjusted bars on already
    # populated Aug/Sep dates. This detects split/dividend/provider-basis mismatch.
    baseline=source[(source['_start']>=pd.Timestamp('2026-09-01T00:00:00Z')) &
                    (source['_start']<pd.Timestamp('2026-09-05T00:00:00Z'))].copy()
    need=set(baseline['_start'].dt.strftime('%Y-%m-%dT%H:%M:%S%z'))
    # staged_dataframe expects isoformat strings with +00:00
    need=set(t.isoformat() for t in baseline['_start'])
    overlap_bars=_fetch_month(session,symbol,frame,pd.Timestamp('2026-08-31T00:00:00Z'),
                             pd.Timestamp('2026-09-06T00:00:00Z'))
    comparison=staged_dataframe(symbol,frame,overlap_bars,need,calendar)
    lhs=baseline.drop_duplicates('_start')[['_start','open','high','low','close']]
    rhs=comparison.rename(columns={'candle_time_utc':'_start'})
    matched=lhs.merge(rhs[['_start','open','high','low','close']],on='_start',suffixes=('_orig','_sip'))
    diffs=[]
    for k in ('open','high','low','close'):
        diffs.extend(((matched[k+'_orig']-matched[k+'_sip']).abs()/matched[k+'_sip'].abs()).tolist())
    max_diff=max(diffs) if diffs else None
    match_min=10 if frame=='15m' else 2
    basis_ok=(len(matched)>=match_min and max_diff is not None and max_diff<=0.002)
    old=pd.DataFrame(columns=staged.columns)
    old_missing_count=len(expected_old)
    old_error=None
    if recover_old and len(expected_old):
        old_gaps=missing[pd.to_datetime(missing['start_utc'],utc=True)<CUT]
        try:
            old, _=stage_missing(symbol,frame,old_gaps,session,calendar,max_months=4)
            if not old.empty:
                old_file=out/f'historical_{symbol}_{frame}.parquet'
                old.to_parquet(old_file,index=False)
            old_missing_count=len(expected_old.difference(pd.DatetimeIndex(pd.to_datetime(old['candle_time_utc'],utc=True))))
        except Exception as e:
            # Do not print credentials or provider responses.
            old_error=type(e).__name__
    report.update({
        'stage_rows':len(staged),'stage_duplicates':duplicate,'stage_overlaps_source':overlap,
        'stage_not_expected':unexpected,'stage_bad_ohlc':staged_bad,
        'missing_recent_before':len(expected_recent),'missing_recent_after':len(not_collected),
        'old_missing_before':len(expected_old),'old_staged':len(old),
        'old_missing_after':old_missing_count,'old_error_type':old_error,
        'price_basis_overlap_points':len(matched),'price_basis_max_rel_ohlc_diff':round(max_diff,8) if max_diff is not None else None,
        'price_basis_pass':basis_ok,'recent_stage_pass':stages_valid,
        'file_sha256':hashes,'source_hash_unchanged':digest(srcpath)==hashes[srcpath.name]
    })
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-dir',type=Path,required=True)
    p.add_argument('--stage-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--as-of',default='2026-10-29')
    p.add_argument('--recover-old',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    cal=xcals.get_calendar('XNYS')
    records=[]
    summary={'status':'RUNNING','as_of':a.as_of,'read_only':True,'source_modified':False,
             'stage_months':['202609','202610'],'datasets':records}
    def save(): (a.out/'validation.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    save()
    for symbol in BASE:
        for frame in FRAMES:
            try:
                src=a.source_dir/f'{symbol}_{frame}.parquet'
                paths=[a.stage_dir/f'{symbol}_{frame}_{m}.parquet' for m in ('202609','202610')]
                with requests.Session() as session:
                    record=validate_one(src,paths,symbol,frame,a.as_of,session,cal,a.out,a.recover_old)
                records.append(record)
                print(json.dumps({k:record[k] for k in ('symbol','timeframe','stage_rows','missing_recent_after','old_staged','old_missing_after','price_basis_overlap_points','price_basis_max_rel_ohlc_diff','price_basis_pass','recent_stage_pass')},ensure_ascii=False),flush=True)
            except Exception as ex:
                records.append({'symbol':symbol,'timeframe':frame,'error_type':type(ex).__name__,'error_message':'Validation stopped; see workflow log without credentials'})
            save()
    passed= len(records)==4 and all(r.get('recent_stage_pass') and r.get('price_basis_pass') and r.get('source_hash_unchanged') for r in records)
    summary['recent_validation_pass']=passed
    summary['recent_staged_rows']=sum(r.get('stage_rows',0) for r in records)
    summary['remaining_old']=sum(r.get('old_missing_after',0) for r in records)
    summary['old_staged_rows']=sum(r.get('old_staged',0) for r in records)
    summary['status']='PASS' if passed and (not a.recover_old or summary['remaining_old']==0) else ('PARTIAL_OLD_GAPS' if passed else 'BLOCKED_VALIDATION')
    save()
    print('FINAL:',summary['status'], 'recent:',summary['recent_staged_rows'], 'historical:',summary['old_staged_rows'], 'old_remaining:',summary['remaining_old'])
    raise SystemExit(0 if summary['status']=='PASS' else 2)

if __name__=='__main__':main()