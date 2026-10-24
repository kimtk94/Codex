"""Research-only staggered entry / horizon sweep. No broker and no live writes."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd

def load(path):
    df=pd.read_csv(path)
    req={'symbol','timestamp','open','high','low','close'}
    if not req.issubset(df): raise ValueError('Missing columns: '+str(sorted(req-set(df))))
    df['timestamp']=pd.to_datetime(df.timestamp,utc=True)
    df=df.sort_values(['symbol','timestamp'])
    if df.duplicated(['symbol','timestamp']).any():raise ValueError('duplicate timestamps')
    for c in ['open','high','low','close']:
        df[c]=pd.to_numeric(df[c],errors='raise')
        if (~np.isfinite(df[c]) | (df[c]<=0)).any():raise ValueError('invalid '+c)
    if (df.high<df[['open','low','close']].max(axis=1)).any() or (df.low>df[['open','high','close']].min(axis=1)).any():raise ValueError('invalid OHLC')
    return df

def simulate(g,start,holding,spacing,legs,tp=.03,sl=.03,fee_bps=0):
    # Entry prices are observed on subsequent minute opens, never from future bars.
    # No replacement for microstructure execution. Each leg independently exits at
    # its own TP/SL or common observation horizon; overall exposure is not assumed free.
    total_cost=0.; total_proceeds=0.; entries=0; stops=0; wins=0
    end=min(start+holding,len(g))
    for j in range(legs):
        idx=start+j*spacing
        if idx>=end:break
        entry=float(g.iloc[idx].open)
        cap=entry*(1+tp);floor=entry*(1-sl)
        price=float(g.iloc[end-1].close)
        for k in range(idx,end):
            bar=g.iloc[k]
            if bar.open<=floor:price=float(bar.open);stops+=1;break
            if bar.open>=cap:price=float(bar.open);wins+=1;break
            if bar.low<=floor:price=floor;stops+=1;break
            if bar.high>=cap:price=cap;wins+=1;break
        total_cost+=entry*(1+fee_bps/10000)
        total_proceeds+=price*(1-fee_bps/10000)
        entries+=1
    if not entries:return None
    return {'return_pct':100*(total_proceeds/total_cost-1),'legs_filled':entries,'tp_hits':wins,'sl_hits':stops}

def run(df,horizons,spacings,legcounts,tp,sl,fees,max_samples=10000):
    rows=[]
    for sym,g in df.groupby('symbol'):
        g=g.reset_index(drop=True)
        # Restrict to genuinely contiguous 1-minute intervals; never bridge overnight gaps.
        blocks=(g.timestamp.diff().dt.total_seconds().fillna(60)!=60).cumsum()
        for _,b in g.groupby(blocks):
            b=b.reset_index(drop=True)
            for h in horizons:
                if len(b)<h:continue
                step=max(1,(len(b)-h+1+max_samples-1)//max_samples)
                for spacing in spacings:
                    for legs in legcounts:
                        r=[]
                        for start in range(0,len(b)-h+1,step):
                            one=simulate(b,start,h,spacing,legs,tp,sl,fees)
                            if one:r.append(one['return_pct'])
                        if not r:continue
                        arr=np.array(r)
                        rows.append({'symbol':sym,'horizon_minutes':h,'spacing_minutes':spacing,'planned_legs':legs,'windows':len(arr),'mean_return_pct':round(float(arr.mean()),5),'win_rate_pct':round(float((arr>0).mean()*100),3),'median_return_pct':round(float(np.median(arr)),5),'p05_return_pct':round(float(np.percentile(arr,5)),5)})
    return pd.DataFrame(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bars',required=True)
    p.add_argument('--out',default='outputs/staggered_sweep')
    p.add_argument('--horizons',default='5,10,20,40,60,100')
    p.add_argument('--spacings',default='1,2,3,5,10')
    p.add_argument('--legs',default='1,2,3,5')
    p.add_argument('--tp',type=float,default=.03)
    p.add_argument('--sl',type=float,default=.03)
    p.add_argument('--fee-bps',type=float,default=0)
    p.add_argument('--max-samples-per-block',type=int,default=2000)
    a=p.parse_args()
    parse=lambda s:sorted(set(int(v) for v in s.split(',')))
    hs,ss,ls=map(parse,(a.horizons,a.spacings,a.legs))
    if any(x<=0 for x in hs+ss+ls) or min(a.tp,a.sl)<=0 or a.fee_bps<0: p.error('nonpositive parameter')
    df=load(a.bars)
    output=run(df,hs,ss,ls,a.tp,a.sl,a.fee_bps,a.max_samples_per_block)
    if output.empty:raise ValueError('No contiguous minute windows; check timestamp granularity and data availability')
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    output.to_csv(out/'sweep.csv',index=False)
    meta={'status':'RESEARCH_ONLY','source':'actual_input_bars','observation_horizons_minutes':hs,
      'horizon_is_provisional':True,'spacing_minutes':ss,'planned_legs':ls,
      'limitations':'Overlapping windows; gross equal-leg performance, NOT real capital-constrained portfolio return/MDD. No R5 signals unless provided externally. No fabricated market data.',
      'data_rows':len(df),'symbols':sorted(df.symbol.unique().tolist()),'evaluated_combinations':len(output)}
    (out/'manifest.json').write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta))

if __name__=='__main__':main()
