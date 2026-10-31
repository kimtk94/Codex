#!/usr/bin/env python3
"""Metadata-only diagnostics for Yahoo USD/KRW OHLC and FRED FX-related nulls.
Reads licensed price snapshots from private ZIP; exports only dates/status and
relative discrepancy metrics, never raw price levels or credentials.
"""
import argparse
import io
import json
from pathlib import Path
import zipfile
import pandas as pd
import numpy as np


def fx_violations(frame):
    cols=['open','high','low','close']
    if not all(k in frame for k in ['timestamp',*cols]):
        raise ValueError('FX_SCHEMA_MISSING')
    d=frame.copy()
    for c in cols:
        d[c]=pd.to_numeric(d[c],errors='coerce')
    bad=(d.high < d[['open','close','low']].max(axis=1)) | (d.low > d[['open','close','high']].min(axis=1))
    bad|=(d[cols].isna().any(axis=1))
    out=d.loc[bad].copy()
    out['date']=pd.to_datetime(out.timestamp,utc=True).dt.strftime('%Y-%m-%d')
    out['open_above_high']=out.open>out.high
    out['open_below_low']=out.open<out.low
    out['close_above_high']=out.close>out.high
    out['close_below_low']=out.close<out.low
    out['high_below_low']=out.high<out.low
    out['has_nan']=out[cols].isna().any(axis=1)
    bound_excess=np.maximum.reduce([
        (out.open-out.high).clip(lower=0).fillna(0).to_numpy(),
        (out.close-out.high).clip(lower=0).fillna(0).to_numpy(),
        (out.low-out.open).clip(lower=0).fillna(0).to_numpy(),
        (out.low-out.close).clip(lower=0).fillna(0).to_numpy(),
        (out.low-out.high).clip(lower=0).fillna(0).to_numpy(),
    ])
    midpoint=out[['high','low','open','close']].median(axis=1)
    out['max_ohlc_violation_bps']=np.where(midpoint>0,bound_excess/midpoint*10000,np.nan)
    return out


def analyze(path:Path, audit_events:Path, output:Path):
    output.mkdir(parents=True,exist_ok=True)
    events=pd.read_csv(audit_events,dtype=str)
    with zipfile.ZipFile(path) as z:
        raw=pd.read_parquet(io.BytesIO(z.read('market/raw/yfinance/yf_usdkrw.parquet')))
        fred=pd.read_csv(io.BytesIO(z.read('fred/fred_latest_revised_long.csv')),
                         dtype={'series_id':str,'observation_date':str})
    invalid=fx_violations(raw)
    # FRED DEXKOUS daily fixing is an independent *indicative* quote with different
    # fixing times; difference is diagnostic only, not an OHLC repair source.
    krw=fred.loc[fred.series_id=='DEXKOUS',['observation_date','value']].drop_duplicates('observation_date')
    krw=krw.rename(columns={'observation_date':'date','value':'fred_fixing'})
    invalid=invalid.merge(krw,on='date',how='left')
    invalid['fred_close_difference_bps']=np.where(
        (invalid.close>0)&(invalid.fred_fixing>0),
        10000*(invalid.close-invalid.fred_fixing).abs()/invalid.fred_fixing,
        np.nan)
    flags=['open_above_high','open_below_low','close_above_high','close_below_low','high_below_low','has_nan']
    ohlc=invalid[['date',*flags,'max_ohlc_violation_bps','fred_close_difference_bps']].copy()
    ohlc['max_ohlc_violation_bps']=ohlc['max_ohlc_violation_bps'].round(5)
    ohlc['fred_close_difference_bps']=ohlc['fred_close_difference_bps'].round(3)
    ohlc.to_csv(output/'fx_ohlc_anomaly_diagnostics.csv',index=False)
    mask=(events.layer=='FRED')&(events.indicator.isin(['DEXKOUS','DTWEXBGS']))&(events.classification=='present_row_null_value')
    f=events.loc[mask,['date','indicator','status','classification']].copy()
    datecounts=f.groupby('date').indicator.nunique()
    f['both_fx_series_missing_same_date']=f.date.map(datecounts).eq(2)
    f['needs_provider_confirmation']=True
    f.sort_values(['date','indicator']).to_csv(output/'fred_fx_unclassified_diagnostics.csv',index=False)
    diagnostics={
        'mode':'READ_ONLY_NO_RAW_PRICE_EXPORT',
        'fx_invalid_ohlc':len(ohlc),
        'fx_max_violation_bps':round(float(ohlc.max_ohlc_violation_bps.max()),5) if len(ohlc) else 0,
        'fx_over_1bps':int((ohlc.max_ohlc_violation_bps>1).sum()),
        'fx_over_10bps':int((ohlc.max_ohlc_violation_bps>10).sum()),
        'fx_fred_crosscheck_available':int(ohlc.fred_close_difference_bps.notna().sum()),
        'fred_fx_unclassified_null_records':len(f),
        'fred_fx_unclassified_distinct_dates':int(f.date.nunique()),
        'fred_fx_joint_missing_dates':int((datecounts==2).sum()),
        'remediation':'no_imputation_no_LIVE_writes; flag invalid rows for exclusion pending alternate-feed check',
        'fred_crosscheck_warning':'FRED DEXKOUS fixing times may not match Yahoo daily close; DO NOT use to rewrite prices',
    }
    (output/'source_diagnostics_summary.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n')
    # Machine-readable guard for future Regime joins; no value imputation or mutation.
    # Technical indicators depend on prior OHLC through rolling/EMA windows. Excluding
    # only the 22 offending dates does not cleanse derived features.
    gates={
        'version':'kalman-research-quality-gates-v1',
        'research_only':True,
        'live_trading_policy_modified':False,
        'asset_guards':{
            'yf_usdkrw':{'ohlc_training_eligible':len(ohlc)==0,
                         'ohlc_anomaly_count':len(ohlc),
                         'invalid_dates':ohlc.date.astype(str).tolist(),
                         'action':'QUARANTINE_UNTIL_INDEPENDENT_PROVIDER_VERIFICATION' if len(ohlc) else 'ALLOW_AFTER_PIT_CHECK'},
            'usd_krw_talib':{'feature_training_eligible':len(ohlc)==0,
                            'action':'QUARANTINE_ALL_DERIVED_FX_TECHNICAL_FEATURES' if len(ohlc) else 'ALLOW_AFTER_PIT_CHECK'},
            'fred_fx_latest_revised':{'vintage_pit_training_eligible':False,
                            'unclassified_null_count':len(f),
                            'action':'REQUIRE_RELEASE_AND_REVISION_AWARE_FEATURES'}
        }
    }
    (output/'feature_eligibility.json').write_text(json.dumps(gates,ensure_ascii=False,indent=2)+'\n')

    print(json.dumps(diagnostics,ensure_ascii=False))
    return diagnostics

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--zip',required=True);p.add_argument('--events',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();analyze(Path(a.zip),Path(a.events),Path(a.out))