#!/usr/bin/env python3
"""Read-only, calendar- and release-frequency-aware missingness audit.
Outputs only dates/status/counts; never publishes licensed prices or secret values.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd
import exchange_calendars as xc
from pandas.tseries.holiday import USFederalHolidayCalendar

MONTHLY={'CPIAUCSL','M2SL','UNRATE'}
WEEKLY={'WALCL'}
ALL_DAYS={'DFF'}
EXCHANGE_FRED={'SP500','NASDAQCOM','VIXCLS'}
GOV_BUSINESS={'DGS2','DFII10','DEXKOUS','DTWEXBGS'}
MARKET_KR={'yf_kospi','yf_kosdaq'}
MARKET_24_7={'yf_btc'}
MARKET_WEEKDAY={'yf_dxy','yf_usdkrw'}
CODES={'valid':'V','null':'N','missing_record':'G','not_expected':'-','market_partial':'P','market_unexpected':'X','feature_warmup':'W','feature_internal':'I'}


def sessions(cal_name,first,last):
    cal=xc.get_calendar(cal_name)
    start=pd.Timestamp(first).normalize()
    end=pd.Timestamp(last).normalize()
    return set(pd.DatetimeIndex(cal.sessions_in_range(start,end)).strftime('%Y-%m-%d'))


def date_keys(first,last,mode):
    left=pd.Timestamp(first);right=pd.Timestamp(last)
    if mode=='calendar': return set(pd.date_range(left,right,freq='D').strftime('%Y-%m-%d'))
    if mode=='business': return set(pd.bdate_range(left,right).strftime('%Y-%m-%d'))
    if mode=='monthly': return set(pd.date_range(left.to_period('M').to_timestamp(),right,freq='MS').strftime('%Y-%m-%d'))
    if mode=='weekly': return set(pd.date_range(left,right,freq='W-WED').strftime('%Y-%m-%d'))
    if mode in ('XNYS','XKRX'): return sessions(mode,left,right)
    raise ValueError('unknown schedule '+str(mode))


def mode_market(key):
    if key in MARKET_24_7 or key=='yf_btc_usd': return 'calendar'
    if key in MARKET_KR: return 'XKRX'
    if key in MARKET_WEEKDAY: return 'business'
    return 'XNYS'


def mode_fred(key):
    if key in MONTHLY:return 'monthly'
    if key in WEEKLY:return 'weekly'
    if key in ALL_DAYS:return 'calendar'
    if key in EXCHANGE_FRED:return 'XNYS'
    return 'business'


@lru_cache(maxsize=1)
def holiday_sets():
    federal=set(USFederalHolidayCalendar().holidays(start='2016-01-01',end='2027-01-01').strftime('%Y-%m-%d'))
    nyse=sessions('XNYS','2016-01-01','2026-12-31')
    return federal,nyse

def prior_holiday_like(d,mode):
    if mode!='business':return False
    federal,nyse=holiday_sets()
    return d in federal or d not in nyse


def audit(input_zip:Path,output_dir:Path,limit_through='2026-10-30'):
    output_dir.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(input_zip) as z:
        names=z.namelist()
        mf=json.loads(z.read('manifest.json'))
        actual={p['path']:hashlib.sha256(z.read(p['path'])).hexdigest() for p in mf['members']}
        failed=[p['path'] for p in mf['members'] if actual[p['path']]!=p['sha256']]
        if failed: raise ValueError('MANIFEST_SHA_MISMATCH:'+','.join(failed[:4]))
        readiness=json.loads(z.read('readiness.json'))
        fred_status=json.loads(z.read('fred/fred_status.json'))
        asof=min(limit_through,readiness['expected_last_completed_nyse_session'])
        events=[];summary=[];date_market={};date_fred={};date_features={};month_rows=[]
        for path in sorted(x for x in names if x.startswith('market/raw/yfinance/') and x.endswith('.parquet')):
            key=Path(path).stem;mode=mode_market(key)
            raw=pd.read_parquet(io.BytesIO(z.read(path)))
            if 'timestamp' not in raw:raise ValueError('BAD_MARKET_TIMESTAMP:'+key)
            datecol=pd.to_datetime(raw.timestamp,errors='coerce',utc=True).dt.strftime('%Y-%m-%d')
            validity={}
            values=['open','high','low','close','volume']
            missing={field:int(raw[field].isna().sum()) if field in raw else len(raw) for field in values}
            for d,part in raw.assign(_date=datecol).groupby('_date',dropna=False):
                if not isinstance(d,str) or len(d)!=10:continue
                bad=[f for f in values if f not in part or part[f].isna().any()]
                invalid_ohlc=False
                if not bad and part['close'].notna().any():
                    invalid_ohlc=bool(((part['low']>part['high']) | (part['high']<part[['open','close']].max(axis=1)) | (part['low']>part[['open','close']].min(axis=1))).any())
                validity[d] = 'P' if bad or invalid_ohlc else 'V'
                if validity[d]!='V':
                    events.append({'layer':'MARKET','indicator':key,'date':d,'status':'PRESENT_INVALID','field':','.join(bad)+('/ohlc' if invalid_ohlc else ''),'frequency':mode,'classification':'observed_missing_or_invalid_price'})
            dupe_count=int(datecol.duplicated().sum())
            for ix in datecol[datecol.duplicated()].index:
                events.append({'layer':'MARKET','indicator':key,'date':str(datecol.loc[ix]),'status':'DUPLICATE_RECORD','field':'timestamp','frequency':mode,'classification':'duplicate_timestamp'})
            if len(validity)==0: raise ValueError('EMPTY_MARKET:'+key)
            start=min(validity);end=min(max(validity),asof)
            expected=date_keys(start,end,mode)
            candidates=[]
            for d in sorted(expected-set(validity)):
                events.append({'layer':'MARKET','indicator':key,'date':d,'status':'GAP','field':'row','frequency':mode,'classification':'missing_expected_session' if mode in ('XNYS','XKRX','calendar') else 'missing_candidate_nonholiday_business_day'})
                candidates.append(d)
            unexpected=[d for d in validity if d<=asof and d not in expected]
            # Weekend entries in FX and index data can be provider session-labeled, not necessarily an error.
            for d in sorted(unexpected):
                events.append({'layer':'MARKET','indicator':key,'date':d,'status':'UNEXPECTED_DATE','field':'timestamp','frequency':mode,'classification':'outside_nominal_calendar_verify_provider_convention'})
            all_dates=set(validity)|expected
            for d in all_dates:
                if d>asof:continue
                date_market.setdefault(d,{})[key]=validity.get(d,'G' if d in expected else '-')
            summary.append({'layer':'MARKET','indicator':key,'schedule':mode,'first_date':start,'last_date':max(validity),'asof_date':asof,'records':len(raw),'duplicate_dates':dupe_count,'expected_session_count':len(expected),'missing_expected_records':len(candidates),'observed_missing_close':missing['close'],'observed_missing_volume':missing['volume'],'partial_dates':sum(x=='P' for x in validity.values()),'unexpected_dates':len(unexpected),'missing_rate_pct':round(100*len(candidates)/max(1,len(expected)),3),'note':'FX business-day gaps are candidates, not confirmed exchange-session holes' if mode=='business' else ''})
        fred=pd.read_csv(io.BytesIO(z.read('fred/fred_latest_revised_long.csv')))
        for key,raw in fred.groupby('series_id'):
            mode=mode_fred(key)
            duplicate_dates=int(raw.observation_date.duplicated().sum())
            for duplicated_date in raw.loc[raw.observation_date.duplicated(),'observation_date']:
                events.append({'layer':'FRED','indicator':key,'date':str(duplicated_date),'status':'DUPLICATE_RECORD','field':'observation_date','frequency':mode,'classification':'duplicate_timestamp'})
            d={str(row.observation_date):('N' if pd.isna(row.value) else 'V') for row in raw.itertuples()}
            start=min(d);end=min(max(d),asof)
            expected=date_keys(start,end,mode)
            invalid=[];missing_rows=[];holiday_null=0
            for dt in sorted(expected):
                v=d.get(dt,'G')
                date_fred.setdefault(dt,{})[key]=v
                if v=='G':
                    missing_rows.append(dt)
                    events.append({'layer':'FRED','indicator':key,'date':dt,'status':'GAP','field':'value','frequency':mode,'classification':'missing_expected_observation_row_candidate'})
                elif v=='N':
                    classification='provider_holiday_or_nonpublication' if prior_holiday_like(dt,mode) else 'present_row_null_value'
                    holiday_null+=int(classification=='provider_holiday_or_nonpublication')
                    invalid.append(dt)
                    events.append({'layer':'FRED','indicator':key,'date':dt,'status':'VALUE_NULL','field':'value','frequency':mode,'classification':classification})
            # A provider may include a null observation on a non-target session; preserve as null, not missing.
            for dt in d.keys()-expected:
                if dt<=asof:
                    date_fred.setdefault(dt,{})[key]=d[dt]
                    if d[dt]=='N':events.append({'layer':'FRED','indicator':key,'date':dt,'status':'VALUE_NULL','field':'value','frequency':mode,'classification':'non_expected_observation_date'})
            valid_dates=[k for k,v in d.items() if v=='V']
            summary.append({'layer':'FRED','indicator':key,'schedule':mode,'first_date':start,'last_date':max(d),'last_valid_date':max(valid_dates) if valid_dates else None,'asof_date':asof,'records':len(raw),'duplicate_dates':duplicate_dates,'expected_session_count':len(expected),'missing_expected_records':len(missing_rows),'observed_missing_value':int(raw.value.isna().sum()),'expected_null_rows':len(invalid),'holiday_like_null_rows':holiday_null,'missing_rate_pct':round(100*len(missing_rows)/max(1,len(expected)),3),'note':'Latest-revised; not vintage PIT. Publication lag after last observation is not counted as a missing record.'})
        for path in sorted(x for x in names if x.startswith('features/talib/') and x.endswith('.parquet')):
            key=Path(path).stem
            f=pd.read_parquet(io.BytesIO(z.read(path)))
            if 'timestamp' not in f: raise ValueError('BAD_FEATURE_TIMESTAMP:'+key)
            d=pd.to_datetime(f.timestamp,errors='coerce',utc=True).dt.strftime('%Y-%m-%d')
            feature_cols=[c for c in f if str(c).startswith('talib_v2_')]
            for col in feature_cols:
                present=f[col].notna().to_numpy()
                first_valid=int(np.argmax(present)) if present.any() else len(present)
                missing_count=int((~present).sum())
                warmup_missing=int((~present[:first_valid]).sum())
                internal_missing=int((~present[first_valid:]).sum())
                summary.append({'layer':'FEATURE','indicator':f'{key}:{col}','schedule':mode_market('yf_'+key),'first_date':str(d.min()),'last_date':str(d.max()),'asof_date':asof,'records':len(f),'expected_session_count':len(f),'observed_missing_value':missing_count,'warmup_missing':warmup_missing,'post_warmup_missing':internal_missing,'missing_rate_pct':round(100*missing_count/max(1,len(f)),3),'note':'post-warmup null candidate; may be caused by raw OHLC missing'})
                for ix in np.flatnonzero(~present):
                    dt=d.iloc[ix]
                    if dt<=asof:
                        typ='W' if ix<first_valid else 'I'
                        events.append({'layer':'FEATURE','indicator':f'{key}:{col}','date':dt,'status':'WARMUP_NULL' if typ=='W' else 'POST_WARMUP_NULL','field':col,'frequency':'daily_derived','classification':'indicator_warmup' if typ=='W' else 'internal_feature_missing_requires_source_check'})
                        date_features.setdefault(dt,{})[f'{key}:{col}']=typ
        all_dates=sorted(set(date_market)|set(date_fred)|set(date_features))
        fields_market=sorted(Path(p).stem for p in names if p.startswith('market/raw/yfinance/') and p.endswith('.parquet'))
        fields_fred=sorted(fred.series_id.unique())
        frame_market=pd.DataFrame.from_dict(date_market,orient='index').reindex(columns=fields_market).fillna('-');frame_market.index.name='date';frame_market.sort_index(inplace=True)
        frame_fred=pd.DataFrame.from_dict(date_fred,orient='index').reindex(columns=fields_fred).fillna('-');frame_fred.index.name='date';frame_fred.sort_index(inplace=True)
        s=pd.DataFrame(summary);e=pd.DataFrame(events)
        if not e.empty:e.sort_values(['date','layer','indicator','status'],inplace=True)
        # Monthly grouped counts, including months with empty observations but expected dates.
        summary_month=[]
        for layer,df in [('MARKET',frame_market),('FRED',frame_fred)]:
            for period,sub in df.groupby(df.index.str[:7]):
                for key in df.columns:
                    col=sub[key]
                    if (col!='-').any():
                        summary_month.append({'month':period,'layer':layer,'indicator':key,
                         'present_valid':int((col=='V').sum()),'present_invalid':int(col.isin(['P','N']).sum()),
                         'missing_expected_record':int((col=='G').sum()),'not_expected':int((col=='-').sum())})
        s.to_csv(output_dir/'indicator_summary.csv',index=False)
        e.to_csv(output_dir/'missing_events.csv',index=False)
        frame_market.to_csv(output_dir/'market_date_matrix.csv')
        frame_fred.to_csv(output_dir/'fred_date_matrix.csv')
        pd.DataFrame(summary_month).to_csv(output_dir/'monthly_missingness.csv',index=False)
        overview={'input_file':input_zip.name,'source_published_utc':mf['published_at_utc'],'asof_date':asof,
          'integrity_files_checked':len(mf['members']),'integrity_failures':failed,
          'market_assets':len(fields_market),'fred_series':len(fields_fred),'feature_series':sum(x['layer']=='FEATURE' for x in summary),
          'raw_fred_null_values':int(fred.value.isna().sum()),
          'raw_fred_rows':len(fred),'market_expected_row_gaps':int(s.loc[s.layer=='MARKET','missing_expected_records'].sum()),
          'fred_missing_expected_records':int(s.loc[s.layer=='FRED','missing_expected_records'].sum()),
          'feature_post_warmup_missing':int(s.loc[s.layer=='FEATURE','post_warmup_missing'].sum()),
          'fred_not_vintage_pit':True,'market_us_calendar':'XNYS','market_kr_calendar':'XKRX',
          'fx_weekdays':'candidate schedule, not authoritative','fred_lag':'not imputed',
          'event_rows':len(e),'notes':['V=valid, N=FRED raw null, P=market partial, G=expected record absent, -=non-applicable','W=TA-Lib initial warmup; I=post-warmup gap','FRED raw null on US holidays is an observed null, not a missing record','No forward-filling or fabricated values']}
        (output_dir/'audit_overview.json').write_text(json.dumps(overview,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps(overview,indent=2,ensure_ascii=False))
        return overview


def main():
    p=argparse.ArgumentParser();p.add_argument('--zip',required=True);p.add_argument('--out',required=True);p.add_argument('--asof',default='2026-10-30')
    a=p.parse_args();audit(Path(a.zip),Path(a.out),a.asof)
if __name__=='__main__': main()