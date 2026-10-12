"""Reproducible September 2026 PAPER CSV metrics; assumes validated input."""
import argparse,csv,json
from pathlib import Path
from upbit_paper_grid_v35 import evaluate_upbit
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--input-dir",required=True);p.add_argument("--out-dir",required=True)
 a=p.parse_args();out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
 rows=[]
 for market in ("KRW-BTC","KRW-ETH"):
  data=Path(a.input_dir)/(market+"_1m_history.csv")
  with data.open(newline="") as f: raw=list(csv.DictReader(f))
  times=[r["t"] for r in raw]
  if len(times)!=len(set(times)) or times!=sorted(times):raise ValueError("bad timestamps")
  if not (times[0].startswith("2026-09-01") and times[-1].startswith("2026-09-30")):
   raise ValueError("Expected full September 2026 input")
  candles=[(r["t"],r["c"]) for r in raw]
  for gap in ("0.14","0.50","1.00"):
   for interval in (0,700):
    result=evaluate_upbit(candles,spacing=gap,anchor_every=interval,fee="0.05")
    result.update(market=market,spacing_pct=gap,recenter_observations=interval,
                  input_rows=len(candles),first=times[0],last=times[-1])
    rows.append(result)
 dest=out/"upbit_v35_sept_sweep.csv"
 with dest.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 manifest={"type":"PAPER_ONLY","cases":len(rows),"data":"Upbit KRW 1m 2026-09",
           "output":str(dest),"fill_model":"close-triggered hypothetical limit fill",
           "limits":["No slippage","No queue position","No partial fills","Fee assumed 0.05% each side","No train/test separation"]}
 (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
 print(json.dumps(manifest))
if __name__=="__main__":main()
