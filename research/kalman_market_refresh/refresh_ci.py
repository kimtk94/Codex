#!/usr/bin/env python3
"""Isolated market-data refresh. No LIVE writes, no trading execution.

Uses existing Kalman market_data/ features_v2_002 CLIs in the workflow.
All output is independently versioned through Drive revisions, and old live files untouched.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode
import zipfile

NEEDED = ('yf_spy','yf_qqq','yf_smh','yf_vix','yf_tnx','yf_hyg','yf_lqd',
          'yf_tlt','yf_gld','yf_dxy','yf_usdkrw')
OPTIONAL = ('yf_iwm','yf_dia','yf_soxx','yf_sp500','yf_ixic','yf_btc',
            'yf_kospi','yf_kosdaq')
FRED_SERIES = ('CPIAUCSL','DEXKOUS','DFF','DFII10','DGS2','DTWEXBGS',
               'M2SL','NASDAQCOM','SP500','UNRATE','VIXCLS','WALCL')


def json_write(path, data):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')


def select_universe(source, dest):
    cfg=json.loads(Path(source).read_text())
    selected=[a for a in cfg['assets'] if a.get('key') in NEEDED+OPTIONAL
              and a.get('provider')=='yfinance']
    got={a['key'] for a in selected}
    missing=set(NEEDED)-got
    if missing:raise ValueError('REQUIRED_NOT_IN_UNIVERSE:'+','.join(sorted(missing)))
    for a in selected: a['required']=a['key'] in NEEDED
    new={'version':'research-daily-market-refresh-v1','assets':selected,'comparisons':[]}
    json_write(dest,new)
    return new


def clean_fred_csv(raw):
    import pandas as pd
    df=pd.read_csv(io.BytesIO(raw),dtype=str)
    df.columns=[str(c).strip().lower() for c in df.columns]
    if len(df.columns)!=2:raise ValueError('FRED_WRONG_COLUMN_COUNT')
    df.columns=['observation_date','value']
    dates=pd.to_datetime(df.observation_date,errors='coerce')
    if dates.isna().any() or dates.duplicated().any():raise ValueError('FRED_BAD_DATE')
    df['value']=pd.to_numeric(df.value.replace('.',float('nan')),errors='coerce')
    if df.value.notna().sum()<20:raise ValueError('FRED_NO_USABLE_DATA')
    return df


def fred_refresh(dest, start='2017-01-01', retries=1):
    """Fetch series concurrently so an unavailable FRED endpoint cannot block market CI."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import requests
    import pandas as pd
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)

    def fetch_one(symbol):
        last_error=''
        for trial in range(retries+1):
            try:
                q=urlencode({'id':symbol,'cosd':start})
                url='https://fred.stlouisfed.org/graph/fredgraph.csv?'+q
                with requests.Session() as session:
                    session.headers['User-Agent']='KalmanResearchDataRefresh/1.0'
                    response=session.get(url,timeout=12)
                response.raise_for_status()
                frame=clean_fred_csv(response.content)
                frame=frame[frame.observation_date>=start].copy()
                frame['series_id']=symbol
                frame['retrieved_at_utc']=datetime.now(timezone.utc).isoformat()
                frame['data_mode']='latest_revised_NOT_ALFRED_PIT'
                return symbol,frame,{'status':'READY','rows':int(frame.value.notna().sum()),
                     'last_observation':str(frame.loc[frame.value.notna(),'observation_date'].max())}
            except Exception as exc:
                last_error=type(exc).__name__
                if trial<retries:time.sleep(0.5)
        return symbol,None,{'status':'FAIL','error_type':last_error}

    frames=[];statuses={}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures=[executor.submit(fetch_one,s) for s in FRED_SERIES]
        for future in as_completed(futures):
            symbol,frame,stat=future.result()
            statuses[symbol]=stat
            if frame is not None:frames.append(frame)
    status={'provider':'FRED_PUBLIC_CSV','status':'READY' if len(frames)==len(FRED_SERIES) else 'DEGRADED',
            'point_in_time_vintage':False,'source_revision':'latest_revised',
            'research_only':True,'not_eligible_for_PIT_training':True,
            'series':{k:statuses[k] for k in FRED_SERIES},'series_ready':len(frames),
            'updated_at':datetime.now(timezone.utc).isoformat()}
    if frames:
        pd.concat(frames,ignore_index=True).sort_values(['series_id','observation_date']).to_csv(out/'fred_latest_revised_long.csv',index=False)
    json_write(out/'fred_status.json',status)
    return status


def verified_status(market_dir, features_dir, fred_dir, required_max_lag_days=7):
    import pandas as pd
    md=Path(market_dir); fd=Path(features_dir);frd=Path(fred_dir)
    run=json.loads((md/'market_data_v2_run_status.json').read_text())
    ft=json.loads((fd/'features_v2_002_run_status.json').read_text())
    fred=json.loads((frd/'fred_status.json').read_text())
    failures=[];checks={}
    now=pd.Timestamp.now(tz='UTC').normalize()
    for key in NEEDED:
        meta=run['sources'].get(key,{})
        path=md/'raw'/'yfinance'/f'{key}.parquet'
        status=meta.get('status')
        if status!='READY' or not path.exists():
            failures.append(f'{key}:SOURCE_{status or "MISSING"}')
            checks[key]={'status':'FAIL','reason':'MISSING_SOURCE'}
            continue
        df=pd.read_parquet(path)
        if len(df)<100 or 'timestamp' not in df or 'close' not in df:
            failures.append(f'{key}:BAD_SCHEMA')
            checks[key]={'status':'FAIL','reason':'BAD_SCHEMA'}
            continue
        timestamps=pd.to_datetime(df.timestamp,utc=True,errors='coerce')
        valid=pd.to_numeric(df.close,errors='coerce').notna()
        if not valid.any() or timestamps[valid].isna().any() or timestamps.duplicated().any():
            failures.append(f'{key}:INVALID_BARS')
            checks[key]={'status':'FAIL','reason':'INVALID_BARS'}
            continue
        last=timestamps[valid].max()
        age=int((now-last.normalize()).days)
        if age>required_max_lag_days or age<0:
            failures.append(f'{key}:STALE_{age}D')
        checks[key]={'status':'READY' if 0<=age<=required_max_lag_days else 'STALE',
                     'rows':len(df),'latest_observation_utc':last.isoformat(),'lag_calendar_days':age}
    if ft.get('required_failures') or ft.get('status')!='READY':
        failures.append('V2_002_FEATURE_FAILURE')
    for key in NEEDED:
        if ft.get('assets',{}).get(key,{}).get('status')!='READY':
            failures.append(f'{key}:FEATURE_FAILURE')
    return {'status':'READY' if not failures else 'BLOCKED',
            'research_only':True,'production_writes':False,
            'point_in_time_training_ready':False,
            'fred_revision_warning':fred.get('source_revision'),
            'created_at':datetime.now(timezone.utc).isoformat(),
            'market_status':run.get('status'),'features_status':ft.get('status'),
            'market_required_checks':checks,'fred_status':fred.get('status'),
            'fred_ready_series':fred.get('series_ready',0),
            'blocking_errors':failures}


def make_bundle(market_dir, features_dir, fred_dir, out, status_path):
    md=Path(market_dir); fd=Path(features_dir);frd=Path(fred_dir)
    status=verified_status(md,fd,frd)
    json_write(status_path,status)
    if status['status']!='READY':
        raise RuntimeError('VALIDATION_BLOCKED:'+';'.join(status['blocking_errors']))
    sources=sorted((md/'raw'/'yfinance').glob('*.parquet'))
    feature_files=sorted((fd/'talib').glob('*.parquet'))
    if len(sources)<len(NEEDED) or len(feature_files)<len(NEEDED):
        raise RuntimeError('INCOMPLETE_MARKET_BUNDLE')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    members=[]
    for base,prefix,paths in [
        (md,'market',sources), (fd,'features',feature_files),
        (frd,'fred',sorted(frd.glob('*.csv'))+sorted(frd.glob('*.json')))]:
        for path in paths: members.append((path,f'{prefix}/{path.relative_to(base)}'))
    manifest={'schema':'kalman-daily-market-research-bundle-v1',
              'status':'RESEARCH_ONLY_VALIDATED','production_writes':False,
              'published_at_utc':status['created_at'], 'price_provider':'yfinance',
              'market_assets':len(sources),'feature_assets':len(feature_files),
              'fred_series_success':status['fred_ready_series'],
              'fred_latest_revised_not_vintage_safe':True,
              'members':[]}
    for file,rel in members:
        manifest['members'].append({'path':rel,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                                    'bytes':file.stat().st_size})
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for file,rel in members:z.write(file,rel)
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        z.writestr('readiness.json',json.dumps(status,indent=2))
    return manifest


def parse_google_credentials():
    from google.oauth2 import service_account
    raw=os.environ.get('CKD_DRIVE_SA_JSON','').strip()
    if not raw:
        b64=os.environ.get('GDRIVE_SA_JSON_B64','').strip()
        if not b64:raise RuntimeError('MISSING_GOOGLE_SERVICE_ACCOUNT_SECRET')
        raw=base64.b64decode(b64,validate=True).decode()
    info=json.loads(raw)
    return service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/drive'])


def publish(out,file_id):
    """Update exactly one pre-shared, research-only existing Drive file; never create in LIVE folders."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{15,100}',file_id):raise ValueError('INVALID_FILE_ID')
    path=Path(out)
    if not path.exists():raise FileNotFoundError(path)
    with zipfile.ZipFile(path) as z:
        mf=json.loads(z.read('manifest.json'))
        if mf.get('status')!='RESEARCH_ONLY_VALIDATED' or mf.get('production_writes') is not False:
            raise RuntimeError('NOT_RESEARCH_BUNDLE')
    import googleapiclient.discovery
    from googleapiclient.http import MediaFileUpload
    service=googleapiclient.discovery.build('drive','v3',credentials=parse_google_credentials(),cache_discovery=False)
    old=service.files().get(fileId=file_id,fields='id,name,mimeType',supportsAllDrives=True).execute()
    if old.get('name')!='kalman_market_research_latest.zip' or old.get('mimeType')!='application/zip':
        raise RuntimeError('UNEXPECTED_TARGET_FILE')
    updated=service.files().update(fileId=file_id,
        media_body=MediaFileUpload(str(path),mimetype='application/zip',resumable=True),
        fields='id,name,size,md5Checksum,modifiedTime',supportsAllDrives=True).execute()
    local=hashlib.md5(path.read_bytes()).hexdigest()
    if updated.get('md5Checksum')!=local:
        raise RuntimeError('DRIVE_MD5_READBACK_MISMATCH')
    # Never emit credential contents
    print(json.dumps({'publish':'VERIFIED','drive_file_id':updated['id'],
        'size':updated.get('size'),'modified_at':updated.get('modifiedTime'),
        'local_md5_verified':True}))


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('universe');a.add_argument('--source',required=True);a.add_argument('--out',required=True)
    a=sub.add_parser('fred');a.add_argument('--out',required=True);a.add_argument('--start',default='2017-01-01')
    a=sub.add_parser('bundle');a.add_argument('--market',required=True);a.add_argument('--features',required=True);a.add_argument('--fred',required=True);a.add_argument('--out',required=True);a.add_argument('--status',required=True)
    a=sub.add_parser('publish');a.add_argument('--file',required=True);a.add_argument('--file-id',required=True)
    a=p.parse_args()
    if a.command=='universe': print(json.dumps({'asset_count':len(select_universe(a.source,a.out)['assets'])}))
    elif a.command=='fred': print(json.dumps(fred_refresh(a.out,a.start)))
    elif a.command=='bundle':print(json.dumps(make_bundle(a.market,a.features,a.fred,a.out,a.status)))
    elif a.command=='publish':publish(a.file,a.file_id)

if __name__=='__main__':main()