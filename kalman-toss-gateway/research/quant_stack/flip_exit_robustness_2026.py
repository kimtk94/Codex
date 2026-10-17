"""Paired uncertainty audit for the frozen 2026 profit-flip policy grid.

Bootstrap groups by NY trading date and by calendar month, not individual bar.
These intervals quantify sampling variation, NOT in-sample selection bias.
"""
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os
import numpy as np

ROOT=Path(os.environ.get("KALMAN_FLIP_RESEARCH_ROOT", "/home/taehoon/kalman-data/trading/research_flip_2026"))
NY=ZoneInfo("America/New_York")
BASE="FLIP_-0.2%"
CANDIDATES=["FLIP_-0.5%","FLIP_-1.0%","FLIP_-1.5%","FLIP_-2.0%","FLIP_OFF"]
rng=np.random.default_rng(20261010)


def bootstrap(rows,candidate,nboot=6000):
    byday=defaultdict(list)
    bymonth=defaultdict(list)
    for r in rows:
        date=datetime.fromisoformat(r["model_entry_time"].replace("Z","+00:00")).astimezone(NY).date()
        delta=(r["scenarios"][candidate]["net"]-r["scenarios"][BASE]["net"])*r["position_weight"]
        byday[str(date)].append(delta)
        bymonth[str(date)[:7]].append(delta)
    intervals={}
    for name,blocks in (("day",byday),("month",bymonth)):
        sums=np.array([sum(v) for v in blocks.values()])
        counts=np.array([len(v) for v in blocks.values()])
        picks=rng.integers(0,len(sums),size=(nboot,len(sums)))
        ratios=sums[picks].sum(axis=1)/counts[picks].sum(axis=1)
        intervals[name]={"block_count":len(sums),"ci95_delta_weighted_pp":
             [round(100*float(x),4) for x in np.quantile(ratios,[.025,.975])],
             "positive_share":round(float(np.mean(ratios>0)),4)}
    return intervals


def main():
    result={}
    for entry_mode in ("","_legacy_entry"):
        path=ROOT/("replay_sip_cost25_0"+entry_mode+"_report.json")
        j=json.loads(path.read_text())
        rows=[r for r in j["detail"] if r["status"]=="PASS"]
        label="sip_next_5m" if not entry_mode else "original_model_reference_entry"
        summary={}
        for candidate in CANDIDATES:
            diffs=np.array([r["scenarios"][candidate]["net"]-r["scenarios"][BASE]["net"] for r in rows])
            w=np.array([r["position_weight"] for r in rows])
            summary[candidate]={
                "paired_n":len(rows),
                "improved":int((diffs>1e-10).sum()),
                "worsened":int((diffs< -1e-10).sum()),
                "identical":int((np.abs(diffs)<=1e-10).sum()),
                "mean_delta_net_pp":round(100*float(diffs.mean()),4),
                "mean_weighted_delta_pp":round(100*float((diffs*w).mean()),4),
                "groups_bootstrap":bootstrap(rows,candidate)
            }
        result[label]=summary
    path=ROOT/"replay_sip_robustness_2026.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
