"""Cost, peer-industry incremental, per-symbol and retention-placebo audit.

All results are time-ordered SHADOW price proxies. This file cannot approve
LIVE trading; historical 2022-2026 years have been examined repeatedly.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

MODELS={"BASELINE":None,"MARKET_FACTOR":"global_selected",
        "INDUSTRY_AND_STOCK":"hierarchical_selected"}
COSTS={"20bp":0.0,"40bp":0.002,"80bp":0.006}
SEED=20261111

def _metric(g,col,cost=0.):
    selected=g if col is None else g.loc[g[col].astype(bool)]
    return {"opportunities":len(g),"selected":len(selected),
        "per_opportunity":float((selected.net_20bp-cost).sum()/len(g)) if len(g) else None,
        "per_selected_trade":float((selected.net_20bp-cost).mean()) if len(selected) else None,
        "selected_negative":int(((selected.net_20bp-cost)<0).sum()),
        "worst_selected":float((selected.net_20bp-cost).min()) if len(selected) else None}

def _random_retention(g,col,iterations,seed):
    if iterations<100:raise ValueError("requires >=100 draws")
    rng=np.random.default_rng(seed)
    values=g.net_20bp.to_numpy(float)
    nselected=int(g[col].astype(bool).sum())
    observed=float(g.loc[g[col].astype(bool),"net_20bp"].sum())
    groups=[]
    for _,sub in g.groupby(["year","industry","event"],sort=True):
        vals=sub.net_20bp.to_numpy(float)
        take=int(sub[col].astype(bool).sum())
        groups.append((vals,take))
    dist=np.zeros(iterations)
    for values,take in groups:
        if take==len(values):
            dist+=values.sum()
        elif take>0:
            for i in range(iterations):
                dist[i]+=rng.choice(values,take,replace=False).sum()
    return {
        "draws":iterations,"selection_control":"year x industry x signal_event",
        "observed_mean_per_opportunity":float(observed/len(g)),
        "random_expected_mean_per_opportunity":float(dist.mean()/len(g)),
        "conditional_ge_fraction":float((1+(dist>=observed-1e-12).sum())/(iterations+1)),
        "not_independent_significance_test":True
    }

def evaluate(pred,iterations=1000):
    required={"date","year","symbol","industry","event","net_20bp","win",
              "industry_model_available","symbol_model_available",
              "global_selected","hierarchical_selected"}
    if required-set(pred):raise ValueError(f"missing columns {sorted(required-set(pred))}")
    if pred.empty:return pd.DataFrame(),pd.DataFrame(),{"status":"HOLD_NO_EVALUATIONS","promotion_allowed":False}
    if pred.duplicated(["date","symbol"]).any():raise ValueError("duplicate signal identity")
    rows=[];annual=[]
    for label,frame in [("ALL",pred),("SECTOR_PEER_PRESENT",pred[pred.industry_model_available])]:
        if frame.empty:continue
        for model,col in MODELS.items():
            for cost,extra in COSTS.items():
                rows.append({"cohort":label,"model":model,"cost":cost,
                             **_metric(frame,col,extra)})
    for (year,industry),g in pred.groupby(["year","industry"]):
        a=_metric(g,"global_selected")
        b=_metric(g,"hierarchical_selected")
        annual.append({"year":int(year),"industry":industry,"n":len(g),
            "market_mean":a["per_opportunity"],
            "hierarchical_mean":b["per_opportunity"],
            "industry_incremental":b["per_opportunity"]-a["per_opportunity"],
            "market_trades":a["selected"],"hierarchical_trades":b["selected"]})
    market=_metric(pred,"global_selected")
    hierarchical=_metric(pred,"hierarchical_selected")
    delta=hierarchical["per_opportunity"]-market["per_opportunity"]
    peer=pred[pred.industry_model_available]
    peer_delta=None
    if len(peer):
        peer_delta=_metric(peer,"hierarchical_selected")["per_opportunity"]-_metric(peer,"global_selected")["per_opportunity"]
    placebo={
        "market":_random_retention(pred,"global_selected",iterations,SEED),
        "hierarchical":_random_retention(pred,"hierarchical_selected",iterations,SEED)
    }
    report={"status":"HOLD_INDUSTRY_INCREMENT_NOT_ESTABLISHED",
       "evaluated":len(pred),
       "market_selected":market["selected"],"hierarchical_selected":hierarchical["selected"],
       "market_net_per_opportunity":market["per_opportunity"],
       "hierarchical_net_per_opportunity":hierarchical["per_opportunity"],
       "hierarchical_increment_vs_market":delta,
       "peer_available_events":len(peer),"peer_increment_vs_market":peer_delta,
       "industry_model_auto_promotion_allowed":False,
       "industry_model_effect_positive_in_revisited_period":bool(delta>0),
       "placebo":placebo,"promotion_allowed":False,
       "warnings":[
         "Price-only nonexecuted events (SIDE_DIP is research-only)",
         "Year x sector x signal episodes share market days; rows not independent",
         "Profitability compared on already explored 2022-2026; no untouched future",
         "Changes in trade count can mimic improvement; placebo conditions on retention counts",
         "Inverse/leverage ETFs and crypto excluded from equity trade-label training"
       ]}
    return pd.DataFrame(rows),pd.DataFrame(annual),report

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--predictions",default="results/regime_countertrend/sector_v3/pooled_industry_symbol_predictions.csv")
    ap.add_argument("--out",default="results/regime_countertrend/sector_v3/ablation")
    a=ap.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if not Path(a.predictions).is_file():
        result={"status":"HOLD_NO_SECTOR_PREDICTIONS","promotion_allowed":False}
    else:
        rows,annual,result=evaluate(pd.read_csv(a.predictions))
        rows.to_csv(out/"costs_and_peer_ablation.csv",index=False)
        annual.to_csv(out/"annual_industry_increment.csv",index=False)
    (out/"decision.json").write_text(json.dumps(result,indent=2))
    print("SECTOR_ABLATION",json.dumps(result))
