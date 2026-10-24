"""Research-only single-symbol cash ledger, sequential non-overlapping windows.
NOT a Kalman signal backtest. Conservative stop-first intrabar fills.
"""
import argparse,json
from pathlib import Path
import numpy as np
from staggered_sweep import load

def evaluate(df,horizon,spacing,legs,capital=1000000.,allocation=.3,tp=.03,sl=.03,fee_bps=5):
    if horizon<1 or spacing<1 or legs<1 or capital<=0 or not 0<allocation<=1:raise ValueError('invalid config')
    if len(df.symbol.unique())!=1:raise ValueError('single-symbol only; no portfolio aggregation across assets')
    df=df.sort_values('timestamp').reset_index(drop=True)
    blocks=(df.timestamp.diff().dt.total_seconds().fillna(60)!=60).cumsum()
    cash=capital; peak=capital; worst_dd=0.; max_exposure=0.; trades=0; fills=0
    equity_points=[]
    for _,b in df.groupby(blocks):
        b=b.reset_index(drop=True)
        for start in range(0,len(b)-horizon+1,horizon):
            positions=[]; end=start+horizon
            per_leg_budget=capital*allocation/legs
            for t in range(start,end):
                bar=b.iloc[t]
                elapsed=t-start
                if elapsed%spacing==0 and elapsed//spacing<legs and cash>=per_leg_budget*(1+fee_bps/10000):
                    entry=float(bar.open);qty=per_leg_budget/entry
                    cash-=per_leg_budget*(1+fee_bps/10000)
                    positions.append((qty,entry));fills+=1
                kept=[]
                for qty,entry in positions:
                    floor=entry*(1-sl);cap=entry*(1+tp)
                    out=None
                    if bar.open<=floor or bar.open>=cap:out=float(bar.open)
                    elif bar.low<=floor:out=floor
                    elif bar.high>=cap:out=cap
                    if out is None:kept.append((qty,entry))
                    else:cash+=qty*out*(1-fee_bps/10000)
                positions=kept
                if t==end-1:
                    for qty,_ in positions:cash+=qty*float(bar.close)*(1-fee_bps/10000)
                    positions=[];trades+=1
                marked=sum(qty*float(bar.close) for qty,_ in positions)
                eq=cash+marked
                peak=max(peak,eq)
                worst_dd=min(worst_dd,100*(eq/peak-1))
                max_exposure=max(max_exposure,marked/eq if eq>0 else 1)
                equity_points.append((str(bar.timestamp),eq))
    return {'status':'RESEARCH_ONLY_NO_KALMAN_SIGNALS','initial_capital':capital,'final_equity':round(cash,4),
            'return_pct':round(100*(cash/capital-1),5),'intrabar_marked_mdd_pct':round(worst_dd,5),
            'max_marked_exposure_pct':round(max_exposure*100,4),'nonoverlap_windows':trades,
            'leg_fills':fills,'equity_points':len(equity_points),
            'limitations':'Single-symbol, chronological windows; no live entry signals, overnight carry, slippage, corporate action adjustment, or cross-asset constraints.'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bars',required=True);p.add_argument('--out',required=True)
    p.add_argument('--capital',type=float,default=1000000)
    p.add_argument('--allocation',type=float,default=.3)
    a=p.parse_args()
    df=load(a.bars);results=[]
    for h in (5,10,20,40,60,100,120,180,240):
        for spacing in (1,3,5,10):
            for legs in (1,2,3,5):
                results.append(dict(horizon_minutes=h,spacing_minutes=spacing,legs=legs,**evaluate(df,h,spacing,legs,a.capital,a.allocation)))
    import pandas as pd
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(results).to_csv(dest/'cash_ledger.csv',index=False)
    (dest/'cash_ledger_manifest.json').write_text(json.dumps({'status':'RESEARCH_ONLY','rows':len(results),
      'capital':a.capital,'allocation':a.allocation,'no_live_execution':True,'no_R5_entry_signals':True},indent=2))
    print(json.dumps({'rows':len(results),'status':'RESEARCH_ONLY'}))
if __name__=='__main__':main()
