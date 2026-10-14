#!/usr/bin/env python3
"""Read-only chronological robustness test for previously fixed grid v3 settings."""
import argparse, subprocess, sys, json, csv
from pathlib import Path
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--engine",default="~/ETH_REGIME_RESEARCH_20261014/upbit_grid_lots_v3.py")
 p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/v3_temporal_validation")
 a=p.parse_args()
 engine=Path(a.engine).expanduser()
 if not engine.is_file():p.error("missing engine")
 root=Path(a.out).expanduser();root.mkdir(parents=True,exist_ok=True)
 periods=[("2026H1_available","2026-02-18","2026-07-01"),("2026JUL_AUG","2026-07-01","2026-09-01"),("2026SEP_OCT09","2026-09-01","2026-10-10")]
 rows=[]
 for label,start,end in periods:
  for cap in (20,30):
   for fee,slip in ((5,2),(10,5)):
    target=root/f"{label}_cap{cap}_fee{fee}_slip{slip}"
    cmd=[sys.executable,str(engine),"--start",start,"--end",end,"--out",str(target),"--initial-krw","1000000","--order-krw","10000","--grid-pct","0.5","--take-profit-pct","0.8","--max-exposure-pct",str(cap),"--fee-bps",str(fee),"--slippage-bps",str(slip)]
    run=subprocess.run(cmd,text=True,capture_output=True)
    if run.returncode:
     print("FAILED",label,cap,fee,run.stderr[-900:]);continue
    s=json.loads((target/"summary.json").read_text())
    rows.append({"period":label,"cap_pct":cap,"fee_bps":fee,"slip_bps":slip,"bars":s["bars"],"return_pct":round(100*s["net_return"],4),"mdd_pct":round(100*s["mdd"],4),"buys":s["buys"],"sells":s["sells"],"open_lots":s["open_lots"],"avg_exposure_pct":round(s["exposure_mean_pct"],3)})
 if rows:
  with (root/"chronological_results.csv").open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps({"status":"COMPLETE" if len(rows)==12 else "PARTIAL","results":rows,"limitations":"Independent resets per period; NOT continuous compounded backtest. Partial 2026H1 availability depends on running backfill. No true untouched holdout after prior exploratory inspection; next-open proxy, not passive limit."},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
