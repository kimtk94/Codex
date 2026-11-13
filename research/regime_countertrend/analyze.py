"""Read-only regime exception research; no LIVE trading changes."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

def analyze(df, gap=5, cost_bps=30):
    required = {"date_ny","close_qld","close_qqq"}
    missing = sorted(required-set(df.columns))
    if missing: raise ValueError("missing columns: "+",".join(missing))
    d = df.copy()
    d["date_ny"] = pd.to_datetime(d["date_ny"],errors="raise")
    d = d.sort_values("date_ny").reset_index(drop=True)
    if d.date_ny.duplicated().any(): raise ValueError("duplicate date_ny")
    if (d[["close_qld","close_qqq"]]<=0).any().any(): raise ValueError("nonpositive close")
    for name, column, k in [("qqq_60d","close_qqq",60),("qqq_20d","close_qqq",20),("qld_5d","close_qld",5),("qqq_5d","close_qqq",5)]:
        d[name]=d[column].pct_change(k)
    d["qqq_future5"]=d.close_qqq.shift(-5)/d.close_qqq-1
    d["qld_future5"]=d.close_qld.shift(-5)/d.close_qld-1
    d["relative_5d"]=d.qld_5d-2*d.qqq_5d
    d["regime"]=np.select([d.qqq_60d>=.08,d.qqq_60d<=-.08],["UP","DOWN"],default="SIDE")
    d["event"]=np.select([(d.regime=="UP")&(d.qld_5d<=-.03),(d.regime=="DOWN")&(d.qld_5d>=.03)],["UP_DIP","DOWN_RALLY"],default="NONE")
    d.loc[d.qqq_60d.isna(),"event"]="NONE"
    candidates=d[(d.event!="NONE")&d.qld_future5.notna()].copy()
    events=[]; last={}
    for i,r in candidates.iterrows():
        if i-last.get(r.event,-999)>=gap:
            events.append(i);last[r.event]=i
    e=d.loc[events].copy()
    e["year"]=e.date_ny.dt.year
    e["net_future5_proxy"]=e.qld_future5-cost_bps/10000
    e["relative_forward5"]=e.qld_future5-2*e.qqq_future5
    columns=["date_ny","year","regime","event","qqq_60d","qqq_20d","qld_5d","qqq_5d","relative_5d","qld_future5","qqq_future5","relative_forward5","net_future5_proxy"]
    return e[columns], {"rows":len(d),"first_date":str(d.date_ny.min().date()),"last_date":str(d.date_ny.max().date()),"event_count":len(e),"event_types":e.event.value_counts().to_dict(),"note":"Exploratory close-to-close proxy, NOT executable backtest; gross and proxy-cost only. Forward targets are excluded from event selection."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True)
    p.add_argument("--out",default="results/regime_countertrend")
    args=p.parse_args()
    events,meta=analyze(pd.read_csv(args.csv))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    events.to_csv(out/"events.csv",index=False)
    (out/"summary.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    print(json.dumps(meta,ensure_ascii=False))
if __name__=="__main__": main()
