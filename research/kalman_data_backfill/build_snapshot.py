#!/usr/bin/env python3
"""Build immutable, research-only QQQ/QLD snapshot. Never update LIVE or source."""
from __future__ import annotations
import argparse,hashlib,json,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import exchange_calendars as xcals
from audit_stage import read_bars,expected_starts

SYMBOLS=('QQQ','QLD')
FRAMES=('15m','1d')
RECENT={'QQQ:15m':988,'QLD:15m':988,'QQQ:1d':38,'QLD:1d':38}
OLD={'QQQ:15m':50,'QLD:15m':3,'QQQ:1d':0,'QLD:1d':0}
BASE_COLS=['market','candle_time_utc','candle_time_kst','open','high',
           'low','close','volume','quote_volume','timestamp_ms','unit_min']

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def canonicalize(frame,symbol,timeframe,provenance):
    f=frame.copy()
    t=pd.DatetimeIndex(f['_start']).tz_convert('UTC')
    f['input_timestamp_utc']=pd.to_datetime(f['candle_time_utc'],utc=True)
    f['candle_time_utc']=t
    f['candle_time_kst']=t.tz_convert('Asia/Seoul')
    f['timestamp_ms']=t.asi8//1000000
    f['unit_min']=15 if timeframe=='15m' else 1440
    f['market']=symbol
    for col in ('open','high','low','close','volume'):
        if col not in f:raise ValueError('Missing required '+col)
        f[col]=pd.to_numeric(f[col],errors='raise')
    f['quote_volume']=pd.to_numeric(f['quote_volume'],errors='coerce') if 'quote_volume' in f else np.nan
    f['provenance']=provenance
    f['adjustment_basis']='Alpaca_SIP_adjusted_all' if provenance!='original' else 'original_unknown'
    return f[BASE_COLS+['input_timestamp_utc','provenance','adjustment_basis']]

def label_gate(expected,observed,cal,sessions_ahead=4):
    """Eligibility uses NEXT four full NYSE sessions; no zero-fill or future labels."""
    if expected.empty:return pd.Series([],dtype=bool)
    present=expected.isin(observed)
    cumulative=np.cumsum((~present).astype(int))
    dates=expected.tz_convert('America/New_York').strftime('%Y-%m-%d')
    sessions=cal.sessions_in_range(dates[0],dates[-1])
    ends={}
    for j,day in enumerate(sessions):
        label=day.date().isoformat()
        ends[label]=int(expected.searchsorted(cal.session_close(sessions[j+sessions_ahead]),side='left')-1) if j+sessions_ahead<len(sessions) else -1
    endidx=np.array([ends[d] for d in dates],dtype=int)
    idx=np.arange(len(expected))
    good=(endidx>idx)&present
    good[good]=cumulative[endidx[good]]==cumulative[idx[good]]
    return pd.Series(good,index=expected)

def make_snapshot(source_dir,stage_dir,historical_zip,validation_json,out,as_of):
    out.mkdir(parents=True,exist_ok=True)
    checks=json.loads(validation_json.read_text())
    if checks.get('recent_validation_pass')!=True or checks.get('recent_staged_rows')!=2052 or checks.get('old_staged_rows')!=50 or checks.get('remaining_old')!=3:
        raise RuntimeError('External data validation gate not satisfied')
    prior={(x['symbol'],x['timeframe']):x for x in checks['datasets']}
    if len(prior)!=4:raise RuntimeError('Expected four validated dataset reports')
    with zipfile.ZipFile(historical_zip) as archive:
        if 'historical_QQQ_15m.parquet' not in archive.namelist():
            raise RuntimeError('Recovered QQQ 50 parquet absent')
        (out/'_tmp_historical.parquet').write_bytes(archive.read('historical_QQQ_15m.parquet'))
    historical=out/'_tmp_historical.parquet'
    cal=xcals.get_calendar('XNYS')
    datasets=[];mask=[];files=[]
    try:
        for symbol in SYMBOLS:
            for tf in FRAMES:
                k=f'{symbol}:{tf}'
                chk=prior[(symbol,tf)]
                if not (chk['recent_stage_pass'] and chk['price_basis_pass'] and chk['source_hash_unchanged']):
                    raise RuntimeError('Provider basis or source gate failed for '+k)
                if chk['stage_rows']!=RECENT[k] or chk['old_missing_before']!=OLD[k]:
                    raise RuntimeError('Counts changed since validation: '+k)
                sources=[('original',source_dir/f'{symbol}_{tf}.parquet')]
                sources += [(f'alpaca_sip_{m}',stage_dir/f'{symbol}_{tf}_{m}.parquet') for m in ('202609','202610')]
                if k=='QQQ:15m':sources.append(('recovered_old_sip',historical))
                frames=[];hashes={}
                for provenance,path in sources:
                    if not path.is_file():raise FileNotFoundError(path)
                    digest=sha256(path)
                    verified=chk.get('file_sha256',{}).get(path.name)
                    if verified and digest!=verified:raise RuntimeError('SOURCE_HASH_CHANGED '+k)
                    hashes[provenance]=digest
                    frames.append(canonicalize(read_bars(path,tf),symbol,tf,provenance))
                df=pd.concat(frames,ignore_index=True)
                df=df.sort_values('candle_time_utc').reset_index(drop=True)
                actual=pd.DatetimeIndex(df['candle_time_utc'])
                if actual.has_duplicates:raise RuntimeError('DUPLICATES '+k)
                if df['volume'].lt(0).any() or df[['open','high','low','close']].isna().any().any() or df[['open','high','low','close']].le(0).any().any():
                    raise RuntimeError('INVALID_PRICES '+k)
                if (df['high']<df[['open','low','close']].max(axis=1)).any() or (df['low']>df[['open','high','close']].min(axis=1)).any():
                    raise RuntimeError('INVALID_OHLC '+k)
                first=actual[0].tz_convert('America/New_York').date().isoformat()
                expect=expected_starts(cal,first,as_of,tf)
                if not actual.isin(expect).all():raise RuntimeError('OFF_SESSION '+k)
                absent=expect.difference(actual)
                if len(absent)!=(3 if k=='QLD:15m' else 0):
                    raise RuntimeError('MISSING_COUNT_CHANGED '+k+' '+str(len(absent)))
                eligible=label_gate(expect,actual,cal)
                df['label_eligible_next_4_sessions']=eligible.loc[actual].to_numpy()
                df['is_interpolated']=False
                df['ny_session_date']=actual.tz_convert('America/New_York').strftime('%Y-%m-%d')
                for t in absent:
                    mask.append({'symbol':symbol,'timeframe':tf,'candle_time_utc':t.isoformat(),'missing_reason':'UNAVAILABLE_SIP_15MIN_AND_COMPLETE_1MIN','is_interpolated':False})
                fn=f'{symbol}_{tf}_research_pit_v1.parquet'
                outpath=out/fn
                df.to_parquet(outpath,index=False)
                files.append(fn)
                datasets.append({'symbol':symbol,'timeframe':tf,'rows':len(df),'expected':len(expect),'missing':len(absent),'first_utc':actual[0].isoformat(),'last_utc':actual[-1].isoformat(),
                    'origin_counts':df['provenance'].value_counts().to_dict(),
                    'label_eligible_next_4_sessions':int(df['label_eligible_next_4_sessions'].sum()),
                    'label_ineligible':int((~df['label_eligible_next_4_sessions']).sum()),
                    'price_basis_max_relative_difference':chk['price_basis_max_rel_ohlc_diff'],'input_sha256':hashes,'output_sha256':sha256(outpath)})
    finally:
        historical.unlink(missing_ok=True)
    missing=pd.DataFrame(mask,columns=['symbol','timeframe','candle_time_utc','missing_reason','is_interpolated'])
    if len(missing)!=3 or set(missing.symbol)!={'QLD'}:raise RuntimeError('Invalid unresolved gap mask')
    missing.to_csv(out/'unresolved_gap_mask.csv',index=False)
    total=sum(x['rows'] for x in datasets)
    if total!=132897:raise RuntimeError('Unexpected total '+str(total))
    manifest={'status':'RESEARCH_ONLY_VALIDATED','version':'pit_v1_20261029','as_of':as_of,'rows_total':total,'missing_bars':3,'recovered_bars':2102,
        'live_policy_modified':False,'source_modified':False,'no_production_promotion':True,
        'warning':'Original-vs-SIP prices can differ up to 0.105%; 0.2% provisional research-only tolerance is not proof of adjustment parity.',
        'label_horizon':'next four full NYSE sessions; any missing future timestamp or censored tail makes the label ineligible',
        'datasets':datasets,'files':files}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    return manifest

def main():
    p=argparse.ArgumentParser()
    for a in ('source-dir','stage-dir','historical-zip','validation-json','out-dir'):p.add_argument('--'+a,type=Path,required=True)
    p.add_argument('--as-of',default='2026-10-29')
    a=p.parse_args()
    r=make_snapshot(a.source_dir,a.stage_dir,a.historical_zip,a.validation_json,a.out_dir,a.as_of)
    print(json.dumps({'status':r['status'],'rows_total':r['rows_total'],'missing_bars':r['missing_bars'],'labels':[(d['symbol'],d['timeframe'],d['label_eligible_next_4_sessions']) for d in r['datasets']]}))

if __name__=='__main__':main()
