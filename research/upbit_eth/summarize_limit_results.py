#!/usr/bin/env python3
"""Summarize existing exploratory grid results; offline, no trading."""
import csv, argparse, collections, statistics
p=argparse.ArgumentParser()
p.add_argument("--csv",default="results_v2_limit/grid_limit_results.csv")
a=p.parse_args()
with open(a.csv,newline="") as f: rows=list(csv.DictReader(f))
for r in rows:
 for k in ("year","levels","fills","skipped_ambiguous_bars","gap_events"): r[k]=int(r[k])
 for k in ("spacing_pct","return_pct","mdd_pct","fee_krw","benchmark_bh_pct"):r[k]=float(r[k])
by_year=collections.defaultdict(list)
for r in rows:by_year[r["year"]].append(r)
for year,rs in sorted(by_year.items()):
 best=sorted(rs,key=lambda r:r["return_pct"],reverse=True)
 print("YEAR",year,"BENCHMARK",round(rs[0]["benchmark_bh_pct"],2),"WINNING_CONFIGS",sum(r["return_pct"]>0 for r in rs))
 for r in best[:5]:
  print(" ",r["spacing_pct"],r["levels"],"return",r["return_pct"],"mdd",r["mdd_pct"],"fills",r["fills"])
by_setting=collections.defaultdict(dict)
for r in rows:by_setting[(r["spacing_pct"],r["levels"])][r["year"]]=r
print("TOP_BY_MIN_YEAR_RETURN (robustness, no hindsight selection):")
def score(item):
 ys=item[1]
 return min(v["return_pct"] for v in ys.values()) if len(ys)==3 else float("-inf")
for (spacing,levels),ys in sorted(by_setting.items(),key=score,reverse=True)[:10]:
 print(spacing,levels," | ".join(str(y)+":"+str(ys[y]["return_pct"]) for y in sorted(ys)),"min",min(x["return_pct"] for x in ys.values()))
print("NOTE: Competing configs in 2025/2026 are not independent after inspecting results. Do not regard top ranking as unbiased OOS proof.")
