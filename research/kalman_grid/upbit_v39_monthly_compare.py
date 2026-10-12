"""PAPER ONLY: evaluate complete independent Upbit months under adverse fee proxies."""
import argparse,csv,json,calendar
from pathlib import Path
from datetime import datetime,timezone
from upbit_data_audit_v28 import audit
from upbit_paper_grid_v35 import evaluate_upbit
from decimal import Decimal

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True)
 p.add_argument("--out-dir",required=True)
 p.add_argument("--months",required=True,help="2026-07,2026-08,2026-09")
 a=p.parse_args();root=Path(a.data_root);out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
 results=[];quality=[]
 for month in a.months.split(","):
  year,mo=map(int,month.split("-"))
  if len(month)!=7 or not 1<=mo<=12:raise ValueError("month format")
  days=calendar.monthrange(year,mo)[1]
  start=f"{year:04d}-{mo:02d}-01T00:00:00+00:00"
  end=f"{year:04d}-{mo:02d}-{days:02d}T23:59:00+00:00"
  for market in ("KRW-BTC","KRW-ETH"):
   path=root/month/(market+"_1m_history.csv")
   q=audit(path,1,start,end);q.update(market=market,month=month);quality.append(q)
   if q["status"]!="PASS":raise ValueError("quality gate blocked: "+str(q))
   with path.open(newline="") as f:obs=[(r["t"],r["c"]) for r in csv.DictReader(f)]
   if not obs or obs[0][0][:7]!=month or obs[-1][0][:7]!=month:raise ValueError("bad input range")
   for gap in ("0.14","0.50","1.00"):
    for mode in (0,700):
     for extra in ("0","0.02","0.05","0.10"):
      fee=str(Decimal("0.05")+Decimal(extra))
      r=evaluate_upbit(obs,spacing=gap,anchor_every=mode,fee=fee)
      r.update(month=month,market=market,spacing_pct=gap,recenter_bars=mode,extra_cost_pct_each_side=extra,assumed_total_fee_pct_each_side=fee)
      results.append(r)
 dest=out/"v39_monthly_cost_results.csv"
 with dest.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 (out/"v39_quality.json").write_text(json.dumps(quality,indent=2))
 (out/"v39_manifest.json").write_text(json.dumps({"scenarios":len(results),"paper_only":True,"month_count":len(a.months.split(",")),"assumption":"close-triggered hypothetical fills; fee-equivalent adverse costs, not real execution slippage"},indent=2))
 print(json.dumps({"status":"COMPLETE","rows":len(results),"csv":str(dest)}))
if __name__=="__main__":main()
