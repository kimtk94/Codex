#!/usr/bin/env python3
"""Compare unchanged v3 on fixed test window under exposure caps. Research-only."""
import argparse,subprocess,sys,json,csv
from pathlib import Path
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--engine",default="~/ETH_REGIME_RESEARCH_20261014/upbit_grid_lots_v3.py")
 p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/v3_cap_sensitivity")
 p.add_argument("--start",default="2026-07-01")
 p.add_argument("--end",default="2026-10-10")
 a=p.parse_args()
 engine=Path(a.engine).expanduser()
 if not engine.exists():raise SystemExit("ENGINE_NOT_FOUND")
 out=Path(a.out).expanduser();out.mkdir(parents=True,exist_ok=True)
 rows=[]
 for cap in (15,20,30):
  folder=out/f"cap_{cap}"
  cmd=[sys.executable,str(engine),"--start",a.start,"--end",a.end,
       "--initial-krw","1000000","--order-krw","10000",
       "--grid-pct","0.5","--take-profit-pct","0.8",
       "--max-exposure-pct",str(cap),"--fee-bps","5",
       "--slippage-bps","2","--out",str(folder)]
  run=subprocess.run(cmd,capture_output=True,text=True)
  if run.returncode:
   print("FAILED",cap,run.stderr[-1800:]);continue
  s=json.loads((folder/"summary.json").read_text())
  rows.append({"cap_pct":cap,"return_pct":round(100*s["net_return"],4),
     "mdd_pct":round(100*s["mdd"],4),"buys":s["buys"],"sells":s["sells"],
     "open_lots":s["open_lots"],"avg_exposure_pct":round(s["exposure_mean_pct"],3),
     "max_exposure_pct":round(s["exposure_max_pct"],3),
     "realized_pnl_krw":round(s["realized_pnl_krw"],2)})
 if rows:
  with (out/"comparison.csv").open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps({"status":"COMPLETE" if len(rows)==3 else "PARTIAL",
   "source":"Unchanged v3 market-order proxy, SAME in-sample history",
   "results":rows,"caution":"No OOS; no passive fill; lowering cap only is not a validated risk policy."},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
