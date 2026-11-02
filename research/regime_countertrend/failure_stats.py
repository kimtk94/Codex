"""Read-only significance audit for countertrend proxy trades."""
import argparse,json
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import fisher_exact

def evaluate(df,bootstrap=3000,seed=42):
    required={"date","year","event","net_return","failed","qqq_dist20"}
    missing=required-set(df)
    if missing:raise ValueError("missing columns: "+str(sorted(missing)))
    d=df.copy();d["failed"]=d.failed.astype(bool);d["below"]=d.qqq_dist20<0
    rng=np.random.default_rng(seed);rows=[]
    for label,g in [("ALL",d)]+list(d.groupby("event")):
        a,b=g[g.below],g[~g.below]
        if not len(a) or not len(b):continue
        table=[[int(a.failed.sum()),int((~a.failed).sum())],[int(b.failed.sum()),int((~b.failed).sum())]]
        _,p=fisher_exact(table)
        x=a.failed.to_numpy();y=b.failed.to_numpy()
        draws=[rng.choice(x,len(x),replace=True).mean()-rng.choice(y,len(y),replace=True).mean() for _ in range(bootstrap)]
        lo,hi=np.quantile(draws,[.025,.975])
        rows.append(dict(event=label,n=len(g),below_n=len(a),below_fail=int(a.failed.sum()),above_n=len(b),above_fail=int(b.failed.sum()),failure_rate_diff=float(x.mean()-y.mean()),fisher_p=float(p),ci_low=float(lo),ci_high=float(hi),holdout_2025_2026_n=int((g.year>=2025).sum())))
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--csv",required=True);ap.add_argument("--out",default="results/regime_countertrend/stats");a=ap.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    e=evaluate(pd.read_csv(a.csv));e.to_csv(out/"failure_ma20_stats.csv",index=False)
    (out/"limitations.json").write_text(json.dumps({"status":"EXPLORATORY","warnings":["IID bootstrap not dependence-aware","unadjusted multiple comparisons","2025-2026 sample small","proxy fills are not LIVE executions"]},indent=2))
    print(e.to_string(index=False))
if __name__=="__main__":main()
