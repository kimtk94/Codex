"""Convert existing intraday parquet/CSV exports to rigorously checked minute OHLC.
Use locally with downloaded historic data. No fabricated 1-minute interpolation.
"""
import argparse,json
from pathlib import Path
import pandas as pd
import numpy as np

ALIASES={
 'symbol':['symbol','ticker','asset','sym'],
 'timestamp':['timestamp','ts','ts_utc','datetime','time','start','t','date_time'],
 'open':['open','o'],'high':['high','h'],'low':['low','l'],'close':['close','c']
}
def convert(df, symbol=None):
    lower={str(k).lower():k for k in df.columns}
    ren={}
    for canonical,choices in ALIASES.items():
        for item in choices:
            if item in lower:
                ren[lower[item]]=canonical;break
    df=df.rename(columns=ren).copy()
    if 'symbol' not in df and symbol:df['symbol']=symbol
    need={'symbol','timestamp','open','high','low','close'}
    if need-set(df):raise ValueError('missing '+str(sorted(need-set(df))))
    # Reject numeric epochs until explicitly mapped: mixed ms/s would be ambiguous.
    if pd.api.types.is_numeric_dtype(df.timestamp):
        raise ValueError('numeric epoch timestamps require explicit units; no inference')
    df['timestamp']=pd.to_datetime(df.timestamp,utc=True,errors='raise')
    for k in ['open','high','low','close']:df[k]=pd.to_numeric(df[k],errors='raise')
    df=df[list(('symbol','timestamp','open','high','low','close'))].sort_values(['symbol','timestamp'])
    if df.duplicated(['symbol','timestamp']).any():raise ValueError('duplicate timestamps')
    if (~np.isfinite(df[['open','high','low','close']].values)).any():raise ValueError('non-finite prices')
    if (df[['open','high','low','close']]<=0).any().any():raise ValueError('negative prices')
    # OHLC plausibility
    if (df.high<df[['open','low','close']].max(axis=1)).any() or (df.low>df[['open','high','close']].min(axis=1)).any():raise ValueError('OHLC inconsistent')
    intervals={}
    for sym,g in df.groupby('symbol'):
        dif=g.timestamp.diff().dt.total_seconds().dropna()
        intervals[sym]={'rows':len(g),'one_minute_edges':int((dif==60).sum()),'edges':len(dif),
           'one_minute_fraction':round(float((dif==60).mean()),5) if len(dif) else 0.0}
    if not any(x['one_minute_edges']>=2 for x in intervals.values()):
        raise ValueError('NOT_1MIN: no verified consecutive 1-minute bars')
    return df,intervals

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True);p.add_argument('--symbol')
    p.add_argument('--out',required=True)
    args=p.parse_args()
    inp=Path(args.input)
    df=pd.read_parquet(inp) if inp.suffix.lower() in ('.parquet','.pq') else pd.read_csv(inp)
    converted,profile=convert(df,args.symbol)
    dst=Path(args.out);dst.parent.mkdir(parents=True,exist_ok=True)
    converted.to_csv(dst,index=False)
    meta={'status':'VERIFIED_1MIN_WITH_GAPS','source':inp.name,
          'rows':len(converted),'symbols':profile,
          'warning':'Continuity is validated per observed edge. Incomplete days and data vendor coverage are not assumed complete.'}
    dst.with_suffix('.profile.json').write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta))
if __name__=='__main__':main()
