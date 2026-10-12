"""Read-only V2.4 hourly-data audit and close-observation sensitivity sweep."""
import argparse, csv, json
from pathlib import Path
from datetime import datetime
from statistics import median
from kalman_grid_v23 import simulate

def read_data(path):
    p=Path(path)
    if p.suffix.lower()=='.parquet':
        import pandas as pd
        d=pd.read_parquet(p)
        ts='t' if 't' in d else 'timestamp'; close='c' if 'c' in d else 'close'
        out=[(str(t),str(v)) for t,v in zip(d[ts],d[close])]
        times=list(pd.to_datetime(d[ts],utc=True))
    else:
        with p.open(newline='') as f:
            reader=csv.DictReader(f);out=[(r.get('t',r.get('timestamp')),r.get('c',r.get('close'))) for r in reader]
        times=[datetime.fromisoformat(t.replace('Z','+00:00')) for t,_ in out]
    if not out: raise ValueError('empty dataset')
    if len(set(t for t,_ in out))!=len(out): raise ValueError('duplicate timestamps')
    if any(times[i]>=times[i+1] for i in range(len(times)-1)): raise ValueError('non increasing timestamps')
    if any(t is None or v is None or float(v)<=0 for t,v in out):raise ValueError('invalid row')
    gap_hours=[(times[i+1]-times[i]).total_seconds()/3600 for i in range(len(times)-1)]
    return out, {'rows':len(out),'first':out[0][0],'last':out[-1][0], 'gaps_gt_2h':sum(x>2 for x in gap_hours),'largest_gap_hours':round(max(gap_hours,default=0),2),'median_step_hours':median(gap_hours) if gap_hours else 0}

def sweep(path,out,spacings=('0.14','0.20','0.30','0.50','1.00'),levels=(20,50,100)):
    rows,quality=read_data(path); results=[]
    for space in spacings:
        for count in levels:
            g,last,n=simulate(rows,spacing=space,levels=count)
            s=g.summary(last)
            results.append({'spacing_pct':space,'levels':count,'bars':n,'return_pct':s['return_pct'],'mdd_pct':s['mdd_pct'],'fills':s['fills'],'realized_pnl':s['realized_pnl'],'fees':s['fees'],'equity':s['equity']})
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    manifest={'data':str(path),'quality':quality,'scenario_count':len(results),'model':'close_only_lower_information_not_return_bound','assumptions':{'entry_order':'one observation per row','fees_pct_one_way':'0.04','intrabar':'NOT MODELED','slippage':'NOT_MODELED','FX_conversion':'NOT_MODELED','corporate_actions':'INPUT_DEPENDENT','venue_rules':'NOT_MODELED'},'output':str(dest),'live_modified':False}
    dest.with_suffix('.json').write_text(json.dumps(manifest,indent=2))
    return manifest

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('--out',default='v24_sweep.csv');a=ap.parse_args();print(json.dumps(sweep(a.input,a.out),indent=2))
