#!/usr/bin/env python3
"""Research-only execution cost stress test of unchanged v3 over same sample.
DO NOT interpret as out-of-sample; no live calls."""
import argparse,csv,json,subprocess,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--engine",default="~/ETH_REGIME_RESEARCH_20261014/upbit_grid_lots_v3.py")
 p.add_argument("--out",default="~/ETH_REGIME_RESEARCH_20261014/v3_cost_stress")
 p.add_argument("--start",default="2026-07-01")
 p.add_argument("--end",default="2026-10-10")
 a=p.parse_args()
 eng=Path(a.engine).expanduser()
 if not eng.is_file():p.error("Engine missing: "+str(eng))
 root=Path(a.out).expanduser();root.mkdir(parents=True,exist_ok=True)
 rows=[]
 for cap in (20,30):
  for fee,slip in ((5,2),(10,5),(20,10)):
   dest=root/f"cap_{cap}_fee_{fee}_slip_{slip}"
   cmd=[sys.executable,str(eng),"--start",a.start,"--end",a.end,
    "--initial-krw","1000000","--order-krw","10000",
    "--grid-pct","0.5","--take-profit-pct","0.8",
    "--max-exposure-pct",str(cap),"--fee-bps",str(fee),
    "--slippage-bps",str(slip),"--out",str(dest)]
   result=subprocess.run(cmd,capture_output=True,text=True)
   if result.returncode:
    print("ERROR",cap,fee,slip,result.stderr[-1000:])
    continue
   s=json.loads((dest/"summary.json").read_text())
   rows.append({"cap_pct":cap,"fee_bps_per_side":fee,"slippage_bps_per_side":slip,
    "return_pct":round(s["net_return"]*100,4),"mdd_pct":round(s["mdd"]*100,4),
    "buys":s["buys"],"sells":s["sells"],"open_lots":s["open_lots"],
    "realized_pnl_krw":round(s["realized_pnl_krw"],2),
    "mean_exposure_pct":round(s["exposure_mean_pct"],4)})
 if rows:
  with (root/"cost_comparison.csv").open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps({"status":"COMPLETE" if len(rows)==6 else "PARTIAL",
  "scenarios":rows,"warning":"Execution proxy only. Same in-sample window; cost stress is not an order-book simulation. Fee and slippage are charged on both entry and exit."},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
