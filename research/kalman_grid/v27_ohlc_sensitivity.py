"""V2.7 OHLC path sensitivity, PAPER ONLY.
Synthetic O-H-L-C vs O-L-H-C sequencing; neither is asserted to be true.
Uses exact same grid engine and cash accounting as V2.6. NO BROKER ACCESS.
"""
import argparse,csv,json
from pathlib import Path
import pandas as pd
from v25_research import evaluate
def pathways(df,order):
    keys={'high_first':('o','h','l','c'),'low_first':('o','l','h','c'),'close_only':('c',)}[order]
    for row in df.itertuples(index=False):
        for key in keys:
            yield (str(row.t),str(getattr(row,key)))
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-dir',required=True)
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--symbols',default='QQQ,QLD')
    ap.add_argument('--spacings',default='0.14,0.5,1.0')
    ap.add_argument('--intervals',default='0,140')
    ap.add_argument('--bars',type=int,default=0,help='0=full history; positive=pilot only')
    a=ap.parse_args()
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    results=[]
    for symbol in a.symbols.split(','):
        df=pd.read_parquet(Path(a.data_dir)/f'{symbol}_1h_2017plus.parquet')
        df=df[['t','o','h','l','c']].sort_values('t')
        if a.bars:df=df.head(a.bars)
        if df.t.duplicated().any() or df[['o','h','l','c']].isna().any().any():raise ValueError('invalid bars')
        if ((df.h<df[['o','l','c']].max(axis=1))|(df.l>df[['o','h','c']].min(axis=1))).any():raise ValueError('OHLC inconsistent')
        for interval in map(int,a.intervals.split(',')):
            for spacing in a.spacings.split(','):
                for path in ('close_only','high_first','low_first'):
                    rows=list(pathways(df,path))
                    r=evaluate(rows,anchor_every=interval*(4 if path!='close_only' else 1),spacing=spacing)
                    r.update(symbol=symbol,interval_in_hourly_bars=interval,spacing_pct=spacing,path=path,source_bars=len(df),start=str(df.t.iloc[0]),end=str(df.t.iloc[-1]))
                    results.append(r)
    with (out/'ohlc_paths.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    manifest={'scenarios':len(results),'pilot':bool(a.bars),'source':'1h OHLC','execution':'PAPER ONLY','limitations':['OHLC cannot reveal actual intrabar order','Four pseudo-observations per bar do not simulate limit queue or depth','Fills at grid price conditional on synthetic path are hypothetical','No FX, slippage, split audit, bid-ask spread or broker rule modeling'],'result':str(out/'ohlc_paths.csv')}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest))
if __name__=='__main__':main()
