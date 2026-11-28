#!/usr/bin/env python3
"""Research-only, strict-match price vs lagged-market features 2025-26 OOS.

Must run beside original kalman_regime_walkforward/engine.py from PR #440.
Original private 15m/1d snapshot and private market ZIP are only read from CI secrets.
Published reports contain NO raw price, source candles, predictions, or credentials.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import exchange_calendars as xcals

sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import (FEATURES,load_verified_zip,make_daily,build_features,create_events,
                    nonoverlap_select,summarize,sha256)

# Each data item represents a completed *prior session* when day D signal is formed.
# FRED latest-revised/vintage data, USDKRW, and FX-dependent features are excluded.
MARKET_KEYS=('yf_vix','yf_hyg','yf_lqd','yf_spy','yf_smh','yf_tnx','yf_tlt','yf_gld','yf_iwm')
MARKET_FEATURES=('m_vix_level','m_vix_change_5','m_credit_hyg_lqd_5','m_spy_5',
                 'm_smh_spy_rel_5','m_10y_change_5','m_tlt_5','m_gld_5','m_iwm_spy_rel_5')
MODEL_SPEC={
    'price_only':list(FEATURES),
    'price_market_core':list(FEATURES)+list(MARKET_FEATURES[:6]),
    'price_market_all':list(FEATURES)+list(MARKET_FEATURES),
}


def load_verified_market(zip_path:Path):
    """Check SHA-256 of every market member and research-only provenance."""
    with zipfile.ZipFile(zip_path) as archive:
        mf=json.loads(archive.read('manifest.json'))
        gate=json.loads(archive.read('readiness.json'))
        if mf.get('status')!='RESEARCH_ONLY_VALIDATED' or mf.get('production_writes') is not False:
            raise ValueError('NOT_RESEARCH_MARKET_SNAPSHOT')
        if gate.get('status')!='READY' or gate.get('production_writes') is not False:
            raise ValueError('MARKET_READINESS_FAIL')
        members={m['path']:m for m in mf['members']}
        for name in ['readiness.json']+['market/raw/yfinance/'+k+'.parquet' for k in MARKET_KEYS]:
            if name!='readiness.json' and name not in members:
                raise ValueError('MISSING_MARKET_ASSET:'+name)
        for path,entry in members.items():
            if hashlib.sha256(archive.read(path)).hexdigest()!=entry['sha256']:
                raise ValueError('MARKET_HASH_MISMATCH:'+path)
        sources={}
        for key in MARKET_KEYS:
            b=archive.read(f'market/raw/yfinance/{key}.parquet')
            df=pd.read_parquet(io.BytesIO(b))
            if not {'timestamp','close'}.issubset(df):raise ValueError('MISSING_MARKET_COLUMNS:'+key)
            d=pd.to_datetime(df.timestamp,utc=True,errors='coerce')
            if d.isna().any() or d.dt.strftime('%Y-%m-%d').duplicated().any():
                raise ValueError('BAD_MARKET_DATES:'+key)
            close=pd.to_numeric(df.close,errors='coerce')
            close=close.where(close>0)
            s=pd.Series(close.to_numpy(float),index=d.dt.strftime('%Y-%m-%d'),name=key).sort_index()
            if s.notna().sum()<400:raise ValueError('MARKET_COVERAGE_TOO_SHORT:'+key)
            sources[key]=s
    return gate,pd.DataFrame(sources)


def lagged_market_features(price_index,market_close):
    """Reindex to NYSE sessions BEFORE lagging: shift one *NYSE trading session*.

    No fill. All source values from D-1 or earlier; Yahoo close isn't stamped
    with a verifiable provider publication instant, so cannot use D same-session.
    """
    m=market_close.reindex(price_index).astype(float)
    for key in MARKET_KEYS:
        if key not in m:raise ValueError('MISSING_MARKET_KEY:'+key)
    def r5(k):return m[k].pct_change(5,fill_method=None)
    v=pd.DataFrame(index=m.index)
    v['m_vix_level']=m['yf_vix']
    v['m_vix_change_5']=r5('yf_vix')
    v['m_credit_hyg_lqd_5']=(m.yf_hyg/m.yf_lqd).pct_change(5,fill_method=None)
    v['m_spy_5']=r5('yf_spy')
    v['m_smh_spy_rel_5']=r5('yf_smh')-r5('yf_spy')
    v['m_10y_change_5']=m['yf_tnx'].diff(5)
    v['m_tlt_5']=r5('yf_tlt')
    v['m_gld_5']=r5('yf_gld')
    v['m_iwm_spy_rel_5']=r5('yf_iwm')-r5('yf_spy')
    return v.shift(1)  # D-1 close is the maximum source date for D decision.


def make_matched_events(events:pd.DataFrame,market:pd.DataFrame,
                        earliest='2024-01-01',latest='2026-10-29'):
    """All candidate strategies share the exact same days, target and price data."""
    e=events[(events.date>=earliest)&(events.date<=latest)].copy()
    if e.empty:raise ValueError('NO_MATCH_CANDIDATES')
    # Include *all* NYSE sessions, even those without a valid QQQ/QLD event.
    # Otherwise a missing event day would move the prior-market lag backward unpredictably.
    cal=xcals.get_calendar('XNYS')
    sessions=cal.sessions_in_range(str(events.date.min()),str(events.date.max()))
    daily_market=lagged_market_features(pd.Index(sessions.strftime('%Y-%m-%d')),market)
    if not daily_market.index.is_unique:raise ValueError('DUPLICATE_PRICE_DATES')
    m=e.merge(daily_market,left_on='date',right_index=True,how='left',validate='one_to_one')
    matched=m.dropna(subset=list(MARKET_FEATURES)+list(FEATURES)).copy().sort_values('date')
    if matched.empty:raise ValueError('NO_COMPLETE_CASE_MARKET_EVENTS')
    if matched.date.duplicated().any():raise ValueError('DUPLICATE_EVENTS')
    report={'candidate_price_days':len(e),'matched_complete_days':len(matched),
            'excluded_incomplete_market_days':len(e)-len(matched),
            'earliest_matched':str(matched.date.min()),'latest_matched':str(matched.date.max()),
            'market_start':str(market.index.min()),'market_end':str(market.index.max()),
            'signal_lag_nyse_sessions':1,'no_market_forward_fill':True}
    return matched,report


def run_matched_walkforward(events,start_year=2025,min_train=150):
    """Expanding-year walk-forward, matured labels, identical training observations.

    Nonoverlap is selected once globally per strategy, then partitioned into
    calendar years and ex-ante QQQ volatility/trend regime. No repeated trades.
    """
    folds=[];tests=[]
    for year in range(start_year,int(events.year.max())+1):
        train=events[(events.date<f'{year}-01-01')&(events.expiry_date<f'{year}-01-01')].copy()
        test=events[events.year==year].copy()
        if test.empty:continue
        if len(train)<min_train or train.target.nunique()!=2:
            folds.append({'year':year,'status':'INSUFFICIENT_MATURE_TRAIN','train':len(train),'test':len(test)})
            continue
        if not str(train.expiry_date.max())<str(test.date.min()):
            raise AssertionError('YEAR_LABEL_PURGE_FAILED')
        for name,cols in MODEL_SPEC.items():
            mdl=make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),
                              LogisticRegression(C=.3,max_iter=2000,random_state=17))
            mdl.fit(train[cols],train.target)
            cutoff=float(np.quantile(mdl.predict_proba(train[cols])[:,1],.70))
            test['signal_'+name]=mdl.predict_proba(test[cols])[:,1]>=cutoff
        test['signal_trend20']=test['qqq_trend_20d']>0
        test['signal_unconditional']=True
        tests.append(test)
        folds.append({'year':year,'status':'OOS','train':len(train),'test':len(test),
                      'train_last_matured':str(train.expiry_date.max()),
                      'test_first_decision':str(test.date.min()),
                      'train_positive_rate':round(float(train.target.mean()),5)})
    if not tests:raise ValueError('NO_OOS_FOLDS')
    oos=pd.concat(tests,ignore_index=True).sort_values('date_index')
    start=str(oos.date.min());end=str(oos.expiry_date.max())
    names=list(MODEL_SPEC)+['trend20','unconditional']
    chosen={name:nonoverlap_select(oos,oos['signal_'+name]) for name in names}
    overall={name:summarize(trades,start,end) for name,trades in chosen.items()}
    byyear=[];byregime=[]
    for name,trades in chosen.items():
        for year in sorted(oos.year.unique()):
            t=trades[trades.year==year]
            y=oos[oos.year==year]
            byyear.append({'strategy':name,'year':int(year),**summarize(t,str(y.date.min()),str(y.expiry_date.max()))})
        for regime in sorted(oos.regime.unique()):
            t=trades[trades.regime==regime]
            byregime.append({'strategy':name,'regime':regime,'trades':len(t),
                'mean_net_trade_pct':round(100*float(t.net_return.mean()),3) if len(t) else None,
                'win_rate_pct':round(100*float((t.net_return>0).mean()),2) if len(t) else None})
        if sum(row['trades'] for row in byyear if row['strategy']==name)!=overall[name]['trades']:
            raise AssertionError('YEAR_COUNTS_DO_NOT_SUM_TO_GLOBAL:'+name)
        if sum(row['trades'] for row in byregime if row['strategy']==name)!=overall[name]['trades']:
            raise AssertionError('REGIME_COUNTS_DO_NOT_SUM_TO_GLOBAL:'+name)
    return {'status':'RESEARCH_MATCHED_OOS_ONLY','start':start,'end':end,
            'source_prices':'QQQ/QLD 15min PIT-research ZIP + Yahoo adjusted-basis-unverified market ZIP',
            'lag_to_market_decision':1,'identical_train_test_candidates':True,
            'fixed_no_reentry_sessions':4,'first_available_next_session_open_proxy':True,
            'cost_per_leg_bps':10,'tp_pct':3,'sl_pct':3,
            'single_position_global_nonoverlap':True,
            'mdd_is_closed_trade_equity_only':True,
            'no_mark_to_market_intratrade_mdd':True,
            'market_provider_publication_time_unverified':True,
            'fred_not_pit_no_macro_training':True,'usdkrw_and_derived_excluded':True,
            'live_modified':False,'macro_expansion_go':False,
            'model_specs':{k:len(v) for k,v in MODEL_SPEC.items()},
            'n_oos_candidates':len(oos),'folds':folds,'strategies':overall,
            'by_year':byyear,'by_regime':byregime}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--price-zip',type=Path,required=True)
    p.add_argument('--market-zip',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    price_manifest,series,gaps=load_verified_zip(args.price_zip,args.out/'_price_temp')
    market_meta,market=load_verified_market(args.market_zip)
    cal=xcals.get_calendar('XNYS')
    daily=make_daily(series,cal)
    feats=build_features(daily)
    events=create_events(daily,feats)
    matched,coverage=make_matched_events(events,market)
    result=run_matched_walkforward(matched)
    result.update({'coverage':coverage,'price_snapshot_sha256':sha256(args.price_zip),
                   'market_snapshot_sha256':sha256(args.market_zip),
                   'price_asof':price_manifest['as_of'],
                   'market_expected_last_session':market_meta.get('expected_last_completed_nyse_session'),
                   'unresolved_QLD_15m_gaps':len(gaps)})
    (args.out/'market_ablation_metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    pd.DataFrame(result['by_year']).to_csv(args.out/'market_ablation_by_year.csv',index=False)
    pd.DataFrame(result['by_regime']).to_csv(args.out/'market_ablation_by_regime.csv',index=False)
    print(json.dumps({'status':result['status'],'oos':result['n_oos_candidates'],
                      'coverage':coverage,'strategies':result['strategies'],
                      'research_only':True},ensure_ascii=False))

if __name__=='__main__':main()