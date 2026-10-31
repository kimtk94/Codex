#!/usr/bin/env python3
"""Read-only research diagnosis of USD/KRW OHLC violations and ambiguous FRED nulls.

Outputs date, flags, distances in basis points and metadata ONLY (never licensed prices).
No imputation, modification of source, or use in LIVE systems.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
import pandas as pd

SOURCE = 'market/raw/yfinance/yf_usdkrw.parquet'
FRED = 'fred/fred_latest_revised_long.csv'


def classify_bar(o, h, l, c):
    """Return structural anomaly types and their maximum severity in basis points."""
    numbers = {'open':o,'high':h,'low':l,'close':c}
    if any(pd.isna(v) for v in numbers.values()):
        return ['MISSING_OHLC'], None
    issues=[]
    if l > h:issues.append('LOW_GREATER_THAN_HIGH')
    if o > h:issues.append('OPEN_ABOVE_HIGH')
    if o < l:issues.append('OPEN_BELOW_LOW')
    if c > h:issues.append('CLOSE_ABOVE_HIGH')
    if c < l:issues.append('CLOSE_BELOW_LOW')
    if min(o,h,l,c) <= 0:issues.append('NONPOSITIVE_PRICE')
    magnitude=max(0, l-h, o-h, l-o, c-h, l-c)
    severity=10000*magnitude/max(abs(c), 1)
    return issues,round(severity,5)


def check_sha(z, member):
    manifest=json.loads(z.read('manifest.json'))
    entries={x['path']:x['sha256'] for x in manifest['members']}
    if member not in entries:
        raise ValueError('MANIFEST_MISSING:'+member)
    if hashlib.sha256(z.read(member)).hexdigest()!=entries[member]:
        raise ValueError('MANIFEST_SHA_MISMATCH:'+member)


def make_training_gate(invalid_dates, unresolved_fred_nulls):
    """Explicit research-only exclusions; do not infer EMA recovery after bad OHLC."""
    dates=sorted(set(str(x) for x in invalid_dates))
    return {
        'schema':'kalman-research-feature-eligibility-v1',
        'live_policy_modified':False,
        'source_ohlc_rewritten':False,
        'asset_guards':{
            'yf_usdkrw':{
                'ohlc_training_eligible':not bool(dates),
                'invalid_dates':dates,
                'reason':'OHLC_INCONSISTENT_WITH_CANDLE_EXTREMA' if dates else 'NO_OHLC_ANOMALIES_DETECTED',
            },
            'usd_krw_talib':{
                'derived_feature_training_eligible':not bool(dates),
                'reason':'DERIVED_FEATURE_LOOKBACK_TAINTED_BY_INVALID_FX_INPUT' if dates else 'PENDING_PIT_CHECK',
            },
            'fred_fx_latest_revised':{
                'historical_vintage_pit_training_eligible':False,
                'unresolved_null_observations':int(unresolved_fred_nulls),
                'reason':'RELEASE_AND_REVISION_PIT_NOT_VERIFIED',
            }
        }
    }


def analyze(src: Path, output: Path):
    output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(src) as z:
        check_sha(z,SOURCE);check_sha(z,FRED)
        readiness=json.loads(z.read('readiness.json'))
        asof=readiness['expected_last_completed_nyse_session']
        if readiness['status']!='READY':raise ValueError('SOURCE_NOT_READY')
        raw=pd.read_parquet(io.BytesIO(z.read(SOURCE)))
        required={'timestamp','open','high','low','close'}
        if not required.issubset(raw.columns):raise ValueError('INVALID_OHLC_SCHEMA')
        dates=pd.to_datetime(raw.timestamp,utc=True,errors='coerce').dt.strftime('%Y-%m-%d')
        fred=pd.read_csv(io.BytesIO(z.read(FRED)))
        context=fred[(fred.series_id=='DEXKOUS')&fred.value.notna()].copy()
        context['value']=pd.to_numeric(context['value'],errors='coerce')
        official={str(x.observation_date):float(x.value) for x in context.itertuples() if pd.notna(x.value)}
        flagged=[]
        for i,row in raw.iterrows():
            day=dates.loc[i]
            if not isinstance(day,str) or day>asof:continue
            issues,bp=classify_bar(row.open,row.high,row.low,row.close)
            if not issues:continue
            ref=official.get(day)
            same_day_bp=(round(abs(float(row.close)/ref-1)*10000,2)
                        if ref and pd.notna(row.close) else None)
            flagged.append({'date':day,'asset':'yf_usdkrw','flags':'|'.join(issues),
                'ohlc_excess_bp':bp,
                'fred_dexkous_same_day_pct_gap':round(same_day_bp/100,4) if same_day_bp is not None else None,
                'fred_same_day_available':bool(ref),
                'status':'REQUIRES_SOURCE_REVIEW',
                'note':'FRED DEXKOUS closing/reference definitions are NOT identical to Yahoo candle definitions; comparison is contextual only'})
        fredgaps=fred[(fred.series_id.isin(['DEXKOUS','DTWEXBGS'])) & (fred.value.isna())].copy()
        # Reuse existing audit classifier: 16 FX nulls remain outside proxy holiday definitions.
        # This is a *candidate* only; a Federal Reserve publication calendar may differ.
        from audit_missingness import prior_holiday_like
        freddetails=[]
        for row in fredgaps.itertuples():
            day=str(row.observation_date)
            if day>asof or prior_holiday_like(day,'business'):continue
            freddetails.append({'date':day,'indicator':row.series_id,
                'classification':'NON_HOLIDAY_PROXY_REQUIRES_PROVIDER_CHECK',
                'status':'PRESERVE_NULL_NO_IMPUTATION'})
        df=pd.DataFrame(flagged,columns=['date','asset','flags','ohlc_excess_bp','fred_dexkous_same_day_pct_gap','fred_same_day_available','status','note']).sort_values('date')
        fg=pd.DataFrame(freddetails,columns=['date','indicator','classification','status']).sort_values(['date','indicator'])
        df.to_csv(output/'usdk_rw_ohlc_diagnostics.csv',index=False)
        pd.DataFrame([{'date':x,'asset':'yf_usdkrw','eligible_for_ohlc_training':False,'reason':'SOURCE_OHLC_NOT_VALIDATED'} for x in df.date],columns=['date','asset','eligible_for_ohlc_training','reason']).to_csv(output/'research_ohlc_exclusion_mask.csv',index=False)
        fg.to_csv(output/'fred_fx_null_diagnostics.csv',index=False)
        flag_count=df['flags'].str.split('|').explode().value_counts().to_dict() if len(df) else {}
        summary={'schema':'kalman-quality-diagnostic-v1','asof':asof,
            'source_revision':readiness.get('created_at'),
            'market_status':readiness.get('status'),
            'fred_status':readiness.get('macro_completeness'),
            'usdkrw_ohlc_issue_dates':len(df),
            'usdkrw_issue_types':flag_count,
            'usdkrw_max_excess_bp':round(float(df.ohlc_excess_bp.max()),5) if len(df) else 0,
            'usdkrw_below_1bp_dates':int((df.ohlc_excess_bp<=1).sum()) if len(df) else 0,
            'fred_fx_null_rows_total':len(fg),
            'fred_fx_nonfederal_candidates':int((fg.classification=='NON_HOLIDAY_PROXY_REQUIRES_PROVIDER_CHECK').sum()),
            'invalid_fred_fx_rows_must_remain_null':True,
            'point_in_time_training_ready':False,
            'production_writes':False,
            'source_prices_published':False,
            'recommendation':'Exclude the 22 flagged USD/KRW bars from OHLC-dependent research until an independently verified provider confirms corrections; do not silently impute FX or FRED.'}
        (output/'quality_diagnostic_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
        (output/'feature_eligibility.json').write_text(
            json.dumps(make_training_gate(df.date, len(fg)),indent=2,ensure_ascii=False)+'\n')
        print(json.dumps(summary,ensure_ascii=False))
        return summary

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--zip',required=True);ap.add_argument('--out',required=True)
    args=ap.parse_args();analyze(Path(args.zip),Path(args.out))