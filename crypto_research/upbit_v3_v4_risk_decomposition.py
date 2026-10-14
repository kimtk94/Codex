#!/usr/bin/env python3
"""Read-only matched-date risk decomposition for v3 vs v4. No trade execution."""
import argparse,json
from pathlib import Path
import pandas as pd
def load(path,style):
 d=pd.read_csv(Path(path).expanduser()/"equity.csv")
 d["ts"]=pd.to_datetime(d.ts,utc=True)
 d=d.sort_values("ts").drop_duplicates("ts")
 d["equity"]=pd.to_numeric(d["equity_krw"])
 d["cost"]=pd.to_numeric(d["capital_krw"] if style=="v3" else d["cost_basis"])
 return d[["ts","equity","cost"]]
def summarize(name,x,initial):
 peak=x.equity.cummax()
 dd=(x.equity/peak-1)
 y=x.copy();y["month"]=y.ts.dt.strftime("%Y-%m")
 monthly=y.groupby("month",sort=True).agg(first=("equity","first"),last=("equity","last"),avg_cost=("cost","mean"),max_cost=("cost","max"))
 return {"name":name,"bars":len(x),"start":str(x.ts.iloc[0]),"end":str(x.ts.iloc[-1]),
   "net_return_pct":round((x.equity.iloc[-1]/initial-1)*100,4),
   "mdd_pct":round(dd.min()*100,4),"mdd_time":str(x.loc[dd.idxmin(),"ts"]),
   "mean_exposure_pct":round(x.cost.mean()/initial*100,4),
   "at_cap_pct_of_bars":round((x.cost>=initial*.2-0.01).mean()*100,3),
   "monthly":[{"month":idx,"delta_equity_krw":round(r["last"]-r["first"],2),
      "avg_exposure_pct":round(r["avg_cost"]/initial*100,3),
      "max_exposure_pct":round(r["max_cost"]/initial*100,3)} for idx,r in monthly.iterrows()]}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--v3",required=True);p.add_argument("--v4",required=True)
 p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/v4_versus_v3_diagnostic.json")
 p.add_argument("--initial-krw",type=float,default=1000000)
 a=p.parse_args()
 x=load(a.v3,"v3");y=load(a.v4,"v4")
 merged=x.merge(y,on="ts",suffixes=("_v3","_v4"),validate="one_to_one")
 if len(merged)!=len(x) or len(merged)!=len(y):raise ValueError("Timestamp mismatch: stop comparison")
 diff=merged.equity_v4-merged.equity_v3
 result={"matched_bars":len(merged),"v3":summarize("v3",x,a.initial_krw),
 "v4":summarize("v4",y,a.initial_krw),
 "v4_minus_v3_final_krw":round(diff.iloc[-1],2),
 "v4_minus_v3_worst_krw":round(diff.min(),2),
 "v4_minus_v3_best_krw":round(diff.max(),2),
 "limitations":"Both equity curves mark unsold ETH at close; no terminal liquidation or orderbook fill, and prior strategy choices used these data."}
 dest=Path(a.out).expanduser();dest.parent.mkdir(exist_ok=True,parents=True)
 dest.write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
