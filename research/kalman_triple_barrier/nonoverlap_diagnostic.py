"""Non-overlapping diagnostic for staggered entry. Research only; no broker."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from staggered_sweep import load,simulate

def evaluate(df,horizons,spacings,legs,tp=.03,sl=.03,fee_bps=5):
    results=[]
    for symbol,g in df.groupby('symbol'):
        g=g.reset_index(drop=True)
        block_id=(g.timestamp.diff().dt.total_seconds().fillna(60)!=60).cumsum()
        blocks=[b.reset_index(drop=True) for _,b in g.groupby(block_id)]
        for h in horizons:
            for spacing in spacings:
                for count in legs:
                    trades=[]
                    for b in blocks:
                        # One position per interval; no overlapping start windows.
                        for start in range(0,len(b)-h+1,h):
                            result=simulate(b,start,h,spacing,count,tp,sl,fee_bps)
                            if result: trades.append(result['return_pct'])
                    if not trades:continue
                    arr=np.array(trades)
                    results.append({'symbol':symbol,'horizon_minutes':h,'spacing_minutes':spacing,
                        'planned_legs':count,'nonoverlap_windows':len(arr),
                        'mean_return_pct':round(float(arr.mean()),5),
                        'win_rate_pct':round(100*float((arr>0).mean()),3),
                        'worst_window_pct':round(float(arr.min()),5),
                        'sample_stdev_pct':round(float(arr.std(ddof=1)),5) if len(arr)>1 else None})
    return pd.DataFrame(results)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bars',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--horizons',default='5,10,20,40,60,100,120,180,240')
    p.add_argument('--spacings',default='1,2,3,5,10')
    p.add_argument('--legs',default='1,2,3,5')
    p.add_argument('--fee-bps',type=float,default=5)
    a=p.parse_args()
    parse=lambda s:[int(v) for v in s.split(',')]
    if a.fee_bps<0:raise ValueError('negative fees')
    result=evaluate(load(a.bars),parse(a.horizons),parse(a.spacings),parse(a.legs),fee_bps=a.fee_bps)
    if result.empty:raise ValueError('NO_NONOVERLAPPING_WINDOWS')
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    result.to_csv(out/'nonoverlap.csv',index=False)
    manifest={'status':'RESEARCH_ONLY','evaluated_combinations':len(result),
      'limitations':'Non-overlapping fixed-horizon intervals but still no out-of-sample signals, equity curve, portfolio MDD or cash constraints. Equal-notional legs; no independent signal or portfolio accounting yet.',
      'no_live_trading':True}
    (out/'nonoverlap_manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest))
if __name__=='__main__':main()
