#!/usr/bin/env python3
"""Research-only, reproducible 15-minute QQQ->QLD regime OOS backtest.

Signals are formed AFTER the last 15m QQQ+QLD candle closes on day D.
Entries are PROXY fills at QLD next trading session's first 15m bar OPEN.
Exit is a 4-trading-session triple barrier; simultaneous hits assume stop first.
No 1m executions, latency, partial fills, market impact, or live policy changes.
Training target is realized TP before SL, with labels fully matured before test.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
import exchange_calendars as xcals
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    'qqq_ret_1d','qqq_ret_5d','qqq_ret_20d', 'qqq_trend_20d',
    'qqq_vol_20d','qqq_vol_ratio','qqq_dd_20d', 'qqq_intraday',
    'qld_ret_1d','qld_ret_5d','qld_ret_20d', 'qld_vol_20d',
    'qld_rel_5d', 'qld_intraday', 'qld_volume_ratio',
]
UTC='UTC'


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_verified_zip(snapshot:Path, out_dir:Path):
    """Explicitly verify research-only provenance and the 4 parquet SHA-256 hashes."""
    out_dir.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(snapshot) as arc:
        manifest=json.loads(arc.read('manifest.json'))
        if manifest.get('status')!='RESEARCH_ONLY_VALIDATED' or manifest.get('no_production_promotion') is not True:
            raise ValueError('RESEARCH_ONLY_MANIFEST_REQUIRED')
        if manifest.get('missing_bars')!=3 or manifest.get('recovered_bars')!=2102:
            raise ValueError('UNEXPECTED_GAP_MANIFEST')
        datasets={}
        for d in manifest['datasets']:
            k=(d['symbol'],d['timeframe'])
            filename=f'{k[0]}_{k[1]}_research_pit_v1.parquet'
            raw=arc.read(filename)
            if hashlib.sha256(raw).hexdigest()!=d['output_sha256']:
                raise ValueError(f'BAD_DATA_HASH:{filename}')
            path=out_dir/filename
            path.write_bytes(raw)
            datasets[k]=pd.read_parquet(path)
        gap_csv=arc.read('unresolved_gap_mask.csv').decode()
        missing=pd.read_csv(__import__('io').StringIO(gap_csv))
        if len(missing)!=3 or set(missing.symbol)!={'QLD'}:
            raise ValueError('MISSING_MASK_NOT_PRESERVED')
    if len(datasets)!=4:raise ValueError('NEED_FOUR_DATASETS')
    return manifest,datasets,missing


def make_daily(bars,cal):
    """Only bars observed by each session's closing time; don't forward-fill gaps."""
    result={}
    sessions=cal.sessions_in_range('2017-01-03','2026-10-29')
    for sym in ('QQQ','QLD'):
        d=bars[(sym,'15m')].copy()
        d['candle_time_utc']=pd.to_datetime(d['candle_time_utc'],utc=True)
        d=d.sort_values('candle_time_utc')
        if d['candle_time_utc'].duplicated().any():raise ValueError('DUPLICATE_BARS:'+sym)
        d['ny_date']=d['candle_time_utc'].dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
        groups={s:g.reset_index(drop=True) for s,g in d.groupby('ny_date')}
        rows=[]
        for sess in sessions:
            day=sess.strftime('%Y-%m-%d')
            expected=pd.date_range(cal.session_open(sess),cal.session_close(sess),freq='15min',inclusive='left')
            group=groups.get(day)
            if group is None or not pd.DatetimeIndex(group['candle_time_utc']).equals(expected):
                rows.append({'date':day,'complete':False,'open':np.nan,'close':np.nan,'high':np.nan,
                             'low':np.nan,'volume':np.nan,'intraday':np.nan})
                continue
            rows.append({'date':day,'complete':True,'open':float(group['open'].iloc[0]),
                         'close':float(group['close'].iloc[-1]), 'high':float(group['high'].max()),
                         'low':float(group['low'].min()),'volume':float(group['volume'].sum()),
                         'intraday':float(group['close'].iloc[-1]/group['open'].iloc[0]-1)})
        daily=pd.DataFrame(rows).set_index('date')
        daily['date_index']=np.arange(len(daily))
        result[sym]=(daily,groups)
    return result


def build_features(daily):
    q=daily['QQQ'][0];l=daily['QLD'][0]
    f=pd.DataFrame(index=q.index)
    for name,x in [('qqq',q),('qld',l)]:
        # pct_change(fill_method=None): prohibit silently padding missing sessions.
        close=x['close'].where(x['complete'])
        daily_return=close.pct_change(fill_method=None)
        for n in (1,5,20): f[f'{name}_ret_{n}d']=close.pct_change(n,fill_method=None)
        f[f'{name}_vol_20d']=daily_return.rolling(20,min_periods=20).std()*np.sqrt(252)
        f[f'{name}_intraday']=x['intraday']
    f['qqq_trend_20d']=q['close']/q['close'].rolling(20,min_periods=20).mean()-1
    f['qqq_vol_ratio']=f['qqq_vol_20d']/q['close'].pct_change(fill_method=None).rolling(60,min_periods=60).std().mul(np.sqrt(252)).replace(0,np.nan)
    f['qqq_dd_20d']=q['close']/q['close'].rolling(20,min_periods=20).max()-1
    f['qld_rel_5d']=f['qld_ret_5d']-2*f['qqq_ret_5d']
    f['qld_volume_ratio']=l['volume']/l['volume'].rolling(20,min_periods=20).median()-1
    f['regime']=np.where(f['qqq_trend_20d']>0,'UP','DOWN')+'_'+np.where(f['qqq_vol_ratio']>1.25,'HIGHVOL','NORMALVOL')
    f['complete_decision_day']=q['complete']&l['complete']
    # Rolling features are strictly computed from observations through D (not D+1).
    f['feature_ready']=f[FEATURES].notna().all(axis=1)&f['complete_decision_day']
    return f


def triple_barrier(next_four,entry_price,tp=0.03,sl=0.03,leg_cost_bps=10):
    """Four complete sessions. Gap-through-stop fills at OPEN; both-hit=stop."""
    if len(next_four)!=4 or any(g is None or g.empty for g in next_four):
        return None
    if not np.isfinite(entry_price) or entry_price<=0:raise ValueError('BAD_ENTRY')
    up=entry_price*(1+tp);down=entry_price*(1-sl)
    px=float(next_four[-1]['close'].iloc[-1]);reason='TIME'
    for g in next_four:
        for row in g.itertuples(index=False):
            o,h,l=float(row.open),float(row.high),float(row.low)
            if o<=down:
                px=o;reason='STOP_GAP';break
            if o>=up:
                px=up;reason='TP_GAP';break
            if l<=down:
                px=down;reason='STOP';break
            if h>=up:
                px=up;reason='TP';break
        if reason!='TIME':break
    cost=leg_cost_bps/10000.0
    net=px*(1-cost)/(entry_price*(1+cost))-1
    return {'outcome':reason,'net_return':float(net),'target':int(reason in ('TP','TP_GAP'))}


def create_events(daily,features,tp=.03,sl=.03,cost_bps=10):
    """Day D signal, next open entry; ensure 4 full sessions are present."""
    q, qbars = daily['QQQ']; l,lbar=daily['QLD']
    days=list(features.index);events=[]
    for i,day in enumerate(days[:-4]):
        feat=features.iloc[i]
        if not bool(feat['feature_ready']):continue
        future_days=days[i+1:i+5]
        if any(not bool(l.loc[d,'complete']) for d in future_days):continue
        groups=[lbar.get(d) for d in future_days]
        entry=float(groups[0]['open'].iloc[0])
        outcome=triple_barrier(groups,entry,tp,sl,cost_bps)
        if outcome is None:continue
        x={k:float(feat[k]) for k in FEATURES}
        x.update({'date':day,'year':int(day[:4]),'date_index':i,'expiry_index':i+4,
                  'expiry_date':future_days[-1], 'regime':feat['regime'],
                  'decision_at_utc':str(qbars[day]['candle_time_utc'].iloc[-1]+pd.Timedelta(minutes=15)),
                  **outcome})
        events.append(x)
    if not events:raise ValueError('NO_VALID_TRAINING_EVENTS')
    df=pd.DataFrame(events)
    if df[FEATURES].isna().any().any():raise AssertionError('MISSING_FEATURES')
    if not (df['expiry_index']>df['date_index']).all():raise AssertionError('FUTURE_LABEL_ERROR')
    return df


def nonoverlap_select(events, signal):
    """Deterministic single-position non-overlap in QLD for four-session exits.

    Conservative: position held for all four sessions even if TP/SL trips sooner;
    therefore no optimistic reinvestment on early barrier exits.
    """
    eligible=events[signal].sort_values('date_index')
    rows=[]; last_exit=-1
    for _,r in eligible.iterrows():
        if int(r.date_index)<=last_exit: continue
        rows.append(r)
        last_exit=int(r.expiry_index)
    return pd.DataFrame(rows,columns=events.columns)


def summarize(trades, first_date, last_date):
    if len(trades):
        a=trades['net_return'].to_numpy(dtype=float)
        eq=np.cumprod(1+a)
        peaks=np.maximum.accumulate(np.r_[1.,eq])
        dd=np.min(np.r_[1.,eq]/peaks-1)
        capital=float(eq[-1])
        wins=float(np.mean(a>0));avg=float(np.mean(a));hit=float(np.mean(trades['target']))
    else:capital=1.;dd=0.;wins=None;avg=None;hit=None
    elapsed=max(1,(pd.Timestamp(last_date)-pd.Timestamp(first_date)).days)
    return {'trades':int(len(trades)),'net_total_return_pct':round((capital-1)*100,3),
            'net_cagr_pct':round((capital**(365.25/elapsed)-1)*100,3) if capital>0 else -100.,
            'trade_win_rate_pct':round(wins*100,2) if wins is not None else None,
            'tp_hit_rate_pct':round(hit*100,2) if hit is not None else None,
            'mean_trade_net_pct':round(avg*100,3) if avg is not None else None,
            'trade_equity_mdd_pct':round(float(dd)*100,3)}


def run_walkforward(events,start_year=2022,cut_quantile=.70):
    predictions=[];folds=[]
    for year in range(start_year,int(events.year.max())+1):
        test=events[events.year==year].copy()
        if test.empty:continue
        # Strict year boundary: no train target can observe outcome inside test year.
        boundary=f'{year}-01-01'
        train=events[(events['expiry_date']<boundary)&(events['date']<boundary)].copy()
        if len(train)<252 or train.target.nunique()<2:
            folds.append({'year':year,'status':'INSUFFICIENT_MATURE_TRAIN','train_count':len(train),'test_count':len(test)});continue
        assert str(train.expiry_date.max())<boundary
        model=make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),
                            LogisticRegression(C=.3,max_iter=2000,random_state=17))
        model.fit(train[FEATURES],train.target)
        train_prob=model.predict_proba(train[FEATURES])[:,1]
        cut=float(np.quantile(train_prob,cut_quantile))
        test['prob_tp']=model.predict_proba(test[FEATURES])[:,1]
        test['trade_model']=test['prob_tp']>=cut
        test['trade_regime']=test['qqq_trend_20d']>0
        test['trade_unconditional']=True
        test['fold']=year
        predictions.append(test)
        folds.append({'year':year,'status':'OOS','train_count':len(train),'test_count':len(test),
                      'train_label_last_date':str(train.expiry_date.max()),
                      'test_first_decision':str(test.date.min()),
                      'training_probability_cut':round(cut,5),
                      'fold_label_positive_rate':round(float(test.target.mean()),5)})
    if not predictions:raise RuntimeError('NO_OOS_FOLDS')
    oos=pd.concat(predictions,ignore_index=True)
    min_date=str(oos.date.min());max_date=str(oos.expiry_date.max())
    # Select a globally nonoverlapping set ONCE, then partition those exact trades
    # into year/regime. Re-selecting inside groups can invent overlapping trades.
    strategy_columns=[('logistic_p70','trade_model'),('trend20','trade_regime'),
                      ('unconditional_QLD','trade_unconditional')]
    selected={name:nonoverlap_select(oos,oos[col]) for name,col in strategy_columns}
    metrics={name:summarize(t,min_date,max_date) for name,t in selected.items()}
    yearly=[];regimes=[]
    for year,g in oos.groupby('year'):
        for name,_ in strategy_columns:
            x=selected[name][selected[name].year==year]
            yearly.append({'year':int(year),'strategy':name,
                **summarize(x,str(g.date.min()),str(g.expiry_date.max()))})
    for regime,g in oos.groupby('regime'):
        t=selected['logistic_p70'][selected['logistic_p70'].regime==regime]
        regimes.append({'regime':regime,'candidate_days':len(g),'model_trade_count':len(t),
                        'mean_net_trade_pct':round(float(t.net_return.mean()*100),3) if len(t) else None,
                        'model_tp_hit_pct':round(float(t.target.mean()*100),2) if len(t) else None})
    for name in selected:
        if sum(x['trades'] for x in yearly if x['strategy']==name)!=metrics[name]['trades']:
            raise AssertionError('YEAR_SUM_DOES_NOT_MATCH_GLOBAL:'+name)
    if sum(x['model_trade_count'] for x in regimes)!=metrics['logistic_p70']['trades']:
        raise AssertionError('REGIME_SUM_DOES_NOT_MATCH_GLOBAL')
    result={'status':'RESEARCH_OOS_ONLY','execution_proxy':'next NYSE session first QLD 15m OPEN',
            'barrier_policy':'4 sessions, TP +3%, SL -3%, same-candle STOP-first',
            'cost_per_leg_bps':10,'fixed_no_reentry_sessions':4,
            'no_1min_execution':True,'no_live_changes':True,
            'oos_from':min_date,'oos_to':max_date,'n_oos_decision_events':len(oos),
            'folds':folds,'strategies':metrics,'by_year':yearly,'by_regime':regimes}
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--snapshot-zip',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--start-year',type=int,default=2022)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    tmp=args.out/'_extract'
    manifest,data,gaps=load_verified_zip(args.snapshot_zip,tmp)
    cal=xcals.get_calendar('XNYS')
    daily=make_daily(data,cal)
    features=build_features(daily)
    events=create_events(daily,features)
    result=run_walkforward(events,args.start_year)
    result['source_snapshot_sha256']=sha256(args.snapshot_zip)
    result['source_as_of']=manifest['as_of']
    result['unresolved_gap_count']=len(gaps)
    (args.out/'walkforward_metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    pd.DataFrame(result['by_year']).to_csv(args.out/'walkforward_by_year.csv',index=False)
    pd.DataFrame(result['by_regime']).to_csv(args.out/'walkforward_by_regime.csv',index=False)
    print(json.dumps({'status':result['status'],'strategies':result['strategies'],'folds':len(result['folds'])},ensure_ascii=False))

if __name__=='__main__':main()