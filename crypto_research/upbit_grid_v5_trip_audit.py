#!/usr/bin/env python3
"""Read-only forensic audit of v5 forced exits/cooldown and cash ledger."""
import argparse,json
from pathlib import Path
import pandas as pd
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--dir",required=True)
 a=p.parse_args(); root=Path(a.dir).expanduser()
 t=pd.read_csv(root/"trades.csv"); e=pd.read_csv(root/"equity.csv")
 summary=json.loads((root/"summary.json").read_text())
 if t.empty: print(json.dumps({"forced_trips":0}));return
 t["ts"]=pd.to_datetime(t.ts,utc=True);e["ts"]=pd.to_datetime(e.ts,utc=True)
 f=t[t.side=="FORCED_EXIT"].copy()
 f["cluster"]=(f.ts!=f.ts.shift()).cumsum()
 trips=[]
 for _,g in f.groupby("cluster",sort=True):
  at=g.ts.iloc[0]
  prev=e[e.ts<at].tail(1)
  nex=t[(t.ts>at)&(t.side=="BUY")].head(1)
  trips.append({"forced_exit_utc":str(at),"forced_lots":int(len(g)),
   "forced_realized_pnl_krw":round(float(g.pnl.sum()),2),
   "equity_prior_observed":float(prev.equity_krw.iloc[0]) if len(prev) else None,
   "next_buy_utc":str(nex.ts.iloc[0]) if len(nex) else None,
   "days_to_next_buy":round((nex.ts.iloc[0]-at).total_seconds()/86400,2) if len(nex) else None})
 out={"directory":str(root),"result_net_return_pct":summary["net_return_pct"],
 "result_mdd_pct":summary["mdd_pct"],"forced_trips":len(trips),"trips":trips,
 "implementation_warning":"In published v5 code highwater is never reset after forced exit. During re-entry, a new mark-to-market loss that is still under prior peak can force liquidation immediately. Treat threshold performance as provisional until tested with and without highwater reset."}
 print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
