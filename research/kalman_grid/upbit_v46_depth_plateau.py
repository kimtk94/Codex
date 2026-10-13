"""PAPER ONLY: select minimum depth preserving max-depth return and fill count per month.

This is a descriptive in-sample plateau, NOT forward optimized or LIVE eligible.
"""
import argparse,csv,json
from pathlib import Path
from collections import defaultdict

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--csv",required=True);p.add_argument("--out",required=True)
 p.add_argument("--tolerance-return-pct-points",type=float,default=0.001)
 a=p.parse_args()
 with open(a.csv,newline="") as f: rows=list(csv.DictReader(f))
 by=defaultdict(list)
 for r in rows:
  if r["status"]=="PAPER_COMPLETE":by[(r["month"],r["gap_pct"])].append(r)
 report=[]
 for (month,gap),items in sorted(by.items()):
  items.sort(key=lambda r:int(r["depth"]))
  ref=items[-1];best=float(ref["return_pct"]);ref_fills=int(ref["fills"])
  same=[r for r in items if abs(float(r["return_pct"])-best)<=a.tolerance_return_pct_points and int(r["fills"])==ref_fills]
  chosen=same[0] if same else ref
  report.append({"month":month,"spacing_pct":gap,"reference_depth":int(ref["depth"]),
   "reference_return_pct":best,"reference_mdd_pct":float(ref["mdd_pct"]),
   "reference_fills":ref_fills,"minimum_equivalent_tested_depth":int(chosen["depth"]),
   "minimum_equivalent_locked_krw":float(chosen["initial_locked_krw"]),
   "return_pct_tolerance_points":a.tolerance_return_pct_points})
 path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps({"status":"DESCRIPTIVE_IN_SAMPLE_ONLY","results":report},indent=2))
 for x in report:print(json.dumps(x),flush=True)
 print(json.dumps({"rows":len(rows),"groups":len(report),"report":str(path)}))
if __name__=="__main__":main()
