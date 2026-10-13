"""PAPER ONLY: 41 spacing sweep with KRW 1m candles; never invokes live services."""
import argparse,csv,json,os
from decimal import Decimal
from pathlib import Path
from upbit_data_audit_v28 import audit
from upbit_paper_grid_v35 import evaluate_upbit

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--data-root",required=True)
 p.add_argument("--out-dir",required=True)
 p.add_argument("--months",default="2026-08,2026-09")
 p.add_argument("--markets",default="KRW-ETH")
 p.add_argument("--cash",default="1000000")
 p.add_argument("--notional",default="5500")
 p.add_argument("--fee",default="0.05")
 p.add_argument("--max-scenarios",type=int,default=0)
 a=p.parse_args()
 root=Path(a.data_root);out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
 spacings=[str(Decimal("0.10")+Decimal("0.01")*i) for i in range(41)]
 months=a.months.split(",");markets=a.markets.split(",")
 results=[]
 for month in months:
  year,mo=map(int,month.split("-"))
  from calendar import monthrange
  finish=monthrange(year,mo)[1]
  start=f"{month}-01T00:00:00+00:00"
  end=f"{month}-{finish:02d}T23:59:00+00:00"
  for market in markets:
   path=root/month/f"{market}_1m_history.csv"
   q=audit(path,1,start,end)
   if q["status"]!="PASS":raise ValueError(f"blocked quality {month} {market}: {q}")
   with path.open(newline="") as f:
    obs=[(r["t"],r["c"]) for r in csv.DictReader(f)]
   for spacing in spacings:
    if a.max_scenarios and len(results)>=a.max_scenarios:break
    row=evaluate_upbit(obs,spacing=spacing,anchor_every=0,fee=a.fee,cash=a.cash,notional=a.notional)
    row.update(month=month,market=market,spacing_pct=spacing,fee_pct_each_side=a.fee,cash_initial=a.cash,notional_per_buy=a.notional)
    results.append(row)
    target=out/"v44_spacing_10_50.csv"
    temp=target.with_suffix(".tmp")
    with temp.open("w",newline="") as handle:
     writer=csv.DictWriter(handle,fieldnames=list(results[0]))
     writer.writeheader();writer.writerows(results)
    os.replace(temp,target)
    print(json.dumps({"month":month,"market":market,"spacing":spacing,"return_pct":row["return_pct"],"mdd_pct":row["mdd_pct"],"fills":row["fills"]}),flush=True)
 summary={"scenario_count":len(results),"paper_only":True,"fee_pct_each_side":a.fee,"cash":a.cash,"notional":a.notional,"limitations":"close-only hypothetical fills, incomplete order-book, fee only; not an executable PnL forecast"}
 (out/"v44_manifest.json").write_text(json.dumps(summary,indent=2))
 print(json.dumps({"status":"COMPLETE","scenarios":len(results),"results_file":str(out/"v44_spacing_10_50.csv")}))
if __name__=="__main__":main()
