from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _load_price(root: Path, symbol: str, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    key = str(symbol).upper().replace('.', '-')
    if key not in cache:
        p = root / f'{key}_1h_gap_aware.parquet'
        if not p.is_file():
            cache[key] = pd.DataFrame()
        else:
            meta = pd.read_parquet(p, columns=['expected_seq','open','close'])
            try:
                ts = pd.read_parquet(p, columns=['timestamp'])['timestamp']
            except Exception:
                ts = pd.read_parquet(p, columns=['candle_time_utc'])['candle_time_utc']
            z = meta.copy()
            z['timestamp'] = ts.values
            z['expected_seq'] = pd.to_numeric(z['expected_seq'], errors='coerce').astype('Int64')
            z['timestamp'] = pd.to_datetime(z['timestamp'], utc=True, errors='coerce')
            z['open'] = pd.to_numeric(z['open'], errors='coerce')
            z['close'] = pd.to_numeric(z['close'], errors='coerce')
            z = z.dropna().drop_duplicates('expected_seq', keep='last').set_index('expected_seq').sort_index()
            cache[key] = z
    return cache[key]


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {'trades': 0}
    r = df['net_return'].astype(float)
    wealth = (1.0 + r).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    start = pd.Timestamp(df.iloc[0]['entry_timestamp'])
    end = pd.Timestamp(df.iloc[-1]['exit_timestamp'])
    years = max((end-start).total_seconds()/(365.25*86400), 1/365.25)
    total = float(wealth.iloc[-1]-1.0)
    cagr = float((1.0+total)**(1.0/years)-1.0) if total > -1 else -1.0
    std = float(r.std(ddof=1)) if len(r)>1 else 0.0
    sharpe = float(r.mean()/std*np.sqrt(252.0)) if std>0 else None
    return {
        'trades': int(len(df)),
        'start': start.isoformat(),
        'end': end.isoformat(),
        'total_return': total,
        'cagr': cagr,
        'max_drawdown': float(dd.min()),
        'mean_net_return': float(r.mean()),
        'median_net_return': float(r.median()),
        'win_rate': float((r>0).mean()),
        'sharpe_trade_ann': sharpe,
        'avg_score_bps': float(df['score_bps'].mean()),
        'median_score_bps': float(df['score_bps'].median()),
    }


def simulate(
    signals: pd.DataFrame,
    price_root: Path,
    *,
    threshold_bps: float,
    horizon_bars: int,
    round_trip_cost_bps: float,
    non_overlap: bool,
) -> pd.DataFrame:
    cache: dict[str, pd.DataFrame] = {}
    rows = []
    blocked_until = -10**18
    for row in signals.sort_values('expected_seq').itertuples(index=False):
        score_bps = float(row.rank1_score) * 10000.0
        if score_bps < threshold_bps:
            continue
        entry_seq = int(row.entry_expected_seq)
        exit_seq = int(row.expected_seq) + int(horizon_bars)
        if non_overlap and entry_seq <= blocked_until:
            continue
        frame = _load_price(price_root, row.rank1_symbol, cache)
        if frame.empty or entry_seq not in frame.index or exit_seq not in frame.index:
            continue
        entry = float(frame.loc[entry_seq, 'open'])
        exit_ = float(frame.loc[exit_seq, 'close'])
        if not np.isfinite(entry) or not np.isfinite(exit_) or entry <= 0:
            continue
        raw = exit_/entry - 1.0
        net = raw - float(round_trip_cost_bps)/10000.0
        rows.append({
            'signal_expected_seq': int(row.expected_seq),
            'entry_expected_seq': entry_seq,
            'exit_expected_seq': exit_seq,
            'symbol': str(row.rank1_symbol),
            'score_bps': score_bps,
            'entry_timestamp': frame.loc[entry_seq, 'timestamp'],
            'exit_timestamp': frame.loc[exit_seq, 'timestamp'],
            'entry_price': entry,
            'exit_price': exit_,
            'raw_return': raw,
            'net_return': net,
        })
        if non_overlap:
            blocked_until = exit_seq
    return pd.DataFrame(rows)


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--panel',type=Path,required=True)
    ap.add_argument('--price-root',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--cost-bps',type=float,required=True)
    ap.add_argument('--thresholds-bps',default='0,10,20,30,36.59673953,45,50')
    ap.add_argument('--horizons',default='4,8,12,20')
    args=ap.parse_args()
    signals=pd.read_parquet(args.panel)
    thresholds=[float(x) for x in args.thresholds_bps.split(',') if x.strip()]
    horizons=[int(x) for x in args.horizons.split(',') if x.strip()]
    args.output_dir.mkdir(parents=True,exist_ok=True)
    summaries=[]
    all_trades=[]
    for non_overlap in (False, True):
        for h in horizons:
            for t in thresholds:
                z=simulate(signals,args.price_root,threshold_bps=t,horizon_bars=h,round_trip_cost_bps=args.cost_bps,non_overlap=non_overlap)
                m=_metrics(z)
                rec={
                    'threshold_bps':t,
                    'horizon_bars':h,
                    'non_overlap':non_overlap,
                    'round_trip_cost_bps':float(args.cost_bps),
                    **m,
                }
                summaries.append(rec)
                if not z.empty:
                    q=z.copy(); q['threshold_bps']=t; q['horizon_bars']=h; q['non_overlap']=non_overlap
                    all_trades.append(q)
    summary=pd.DataFrame(summaries)
    summary['candidate_gate']=np.where(
        (summary.get('trades',0)>=30)&(summary.get('cagr',-1)>0)&(summary.get('total_return',-1)>0),
        'CANDIDATE_RETRAIN_VALIDATE','REJECT'
    )
    summary=summary.sort_values(['candidate_gate','cagr','trades'],ascending=[True,False,False])
    summary.to_csv(args.output_dir/'summary.csv',index=False)
    if all_trades:
        pd.concat(all_trades,ignore_index=True).to_parquet(args.output_dir/'trades.parquet',index=False)
    candidates=summary.loc[summary['candidate_gate'].eq('CANDIDATE_RETRAIN_VALIDATE')].copy()
    status={
        'schema_version':'r5-2-cost-aware-overlay-v1',
        'status':'COMPLETE',
        'exploratory_only':True,
        'important_limitation':'Current R5.1 score was trained for ~4H target; longer horizons are exploratory and require horizon-specific retraining before promotion.',
        'cost_bps':float(args.cost_bps),
        'scenarios':int(len(summary)),
        'candidate_scenarios':int(len(candidates)),
        'top_10':summary.head(10).replace({np.nan:None}).to_dict(orient='records'),
    }
    (args.output_dir/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps(status,ensure_ascii=False,indent=2,default=str))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
