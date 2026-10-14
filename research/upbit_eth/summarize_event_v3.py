#!/usr/bin/env python3
"""Read-only summary of KRW-ETH v3 annual event-grid results. Python stdlib only."""
import argparse,csv,collections,json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--csv",default="results_event_v3/grid_event_results.csv")
p.add_argument("--out",default="results_event_v3/summary_v3.json")
a=p.parse_args()
with open(a.csv,newline="") as f: rows=list(csv.DictReader(f))
if not rows:raise SystemExit("Empty CSV")
for r in rows:
 for k in ("year","levels","fills"):r[k]=int(r[k])
 for k in ("spacing_pct","return_pct","mdd_pct"):r[k]=float(r[k])
 r["fees_krw"]=float(r.get("fees_krw",r.get("fee_krw",0)))
 r["turnover_krw"]=float(r.get("turnover_krw",0))
by_year=collections.defaultdict(list);by_config=collections.defaultdict(dict)
for r in rows:
 by_year[r["year"]].append(r)
 key=(round(r["spacing_pct"],4),r["levels"])
 if r["year"] in by_config[key]:raise SystemExit("Duplicate config-year")
 by_config[key][r["year"]]=r
summary={"years":{},"configurations":[],"notes":[
 "These are annual reset-inventory results, not a three-year continuous return.",
 "Intrabar execution, historical order queues and exchange availability are unverified.",
 "Ranking across all three years uses hindsight; it is descriptive, not unbiased out-of-sample validation.",
 "A config qualifies only when each annual return >=10% and each MDD >=-20%."]}
for year,rs in sorted(by_year.items()):
 top=sorted(rs,key=lambda r:r["return_pct"],reverse=True)
 summary["years"][str(year)]={"tested":len(rs),"positive":sum(r["return_pct"]>0 for r in rs),"pass_both":sum(r["return_pct"]>=10 and r["mdd_pct"]>=-20 for r in rs),"top_5":[{k:r[k] for k in ("spacing_pct","levels","return_pct","mdd_pct","fills","fees_krw")} for r in top[:5]]}
 print("YEAR",year,"TESTED",len(rs),"PROFITABLE",summary["years"][str(year)]["positive"],"PASS_TARGET",summary["years"][str(year)]["pass_both"])
 for r in top[:5]:print(" ",r["spacing_pct"],r["levels"],"RET",r["return_pct"],"MDD",r["mdd_pct"],"FILLS",r["fills"])
for key,years in by_config.items():
 if set(years)!={2024,2025,2026}:continue
 vals=[years[y] for y in (2024,2025,2026)]
 summary["configurations"].append({"spacing_pct":key[0],"levels":key[1],
  "returns_by_year":{str(y):years[y]["return_pct"] for y in sorted(years)},
  "mdd_by_year":{str(y):years[y]["mdd_pct"] for y in sorted(years)},
  "worst_return_pct":min(v["return_pct"] for v in vals),
  "worst_mdd_pct":min(v["mdd_pct"] for v in vals),
  "pass_all_years":all(v["return_pct"]>=10 and v["mdd_pct"]>=-20 for v in vals)})
summary["configurations"].sort(key=lambda r:(r["pass_all_years"],r["worst_return_pct"]),reverse=True)
print("THREE_YEAR_CONSISTENCY")
for r in summary["configurations"][:10]:print(r["spacing_pct"],r["levels"],r["returns_by_year"],"WORST_MDD",r["worst_mdd_pct"],"PASS",r["pass_all_years"])
out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print("SAVED",out)
