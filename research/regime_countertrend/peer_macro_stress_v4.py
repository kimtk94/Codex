"""CFM-V4 exact-model ablations and stress gates; NO tuning on revisited years.

Separates the ETF macro contribution from symbol and historical peer transfers.
The historical 2022-2026 window was repeatedly inspected and is not an
untouched holdout; all results are research-only, with LIVE blocked.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

from .sector_ablation_v3 import _random_retention

THRESHOLD=.55
PEER_WEIGHT=.30
SYMBOL_WEIGHT=.20
ADDITIONAL_COST={"20bp":0.0,"40bp":0.002,"80bp":0.006}

def prepare(pred):
    required={"year","date","symbol","industry","event","win","net_20bp",
       "macro_market_probability","peer_probability","symbol_probability",
       "macro_market_selected","macro_peer_selected","peer_available","symbol_available"}
    if required-set(pred):raise ValueError("missing model fields")
    if pred.duplicated(["symbol","date"]).any():raise ValueError("duplicate signal")
    d=pred.copy()
    market=d.macro_market_probability.to_numpy(dtype=float)
    peer=d.peer_probability.to_numpy(dtype=float)
    sym=d.symbol_probability.to_numpy(dtype=float)
    has_peer=d.peer_available.astype(bool).to_numpy()
    has_symbol=d.symbol_available.astype(bool).to_numpy()
    if not np.isfinite(market).all() or not np.isfinite(d.net_20bp).all():
        raise ValueError("invalid base probabilities or returns")
    if (has_peer & ~np.isfinite(peer)).any() or (has_symbol & ~np.isfinite(sym)).any():
        raise ValueError("available peer/symbol score is missing")
    # All peer/symbol probabilities are FOLD-TRAINED beforehand; we do not
    # recompute models or select mixture coefficients from current-year PnL.
    peer_only=(1-PEER_WEIGHT*has_peer)*market+PEER_WEIGHT*np.nan_to_num(peer,nan=0)
    symbol_only=(1-SYMBOL_WEIGHT*has_symbol)*market+SYMBOL_WEIGHT*np.nan_to_num(sym,nan=0)
    both=(1-PEER_WEIGHT*has_peer-SYMBOL_WEIGHT*has_symbol)*market + (
        PEER_WEIGHT*np.nan_to_num(peer,nan=0)+
        SYMBOL_WEIGHT*np.nan_to_num(sym,nan=0))
    if not np.allclose(both,d.macro_peer_probability,atol=1e-12,rtol=1e-12):
        raise ValueError("original V4 peer+symbol mixture mismatch")
    if not np.array_equal(d.macro_peer_selected.astype(bool).to_numpy(),both>=THRESHOLD):
        raise ValueError("original V4 selected flags inconsistent")
    d["macro_peer_only_selected"]=peer_only>=THRESHOLD
    d["macro_symbol_only_selected"]=symbol_only>=THRESHOLD
    return d

def _measure(x,selector,cost):
    eligible=x if selector is None else x.loc[x[selector].astype(bool)]
    n=len(x)
    returns=eligible.net_20bp.to_numpy(dtype=float)-cost
    return {"opportunities":n,"selected":len(eligible),
      "net_per_opportunity":float(returns.sum()/n) if n else None,
      "net_per_selected":float(returns.mean()) if len(returns) else None,
      "negative_selected":int((returns<0).sum()),
      "worst_selected":float(returns.min()) if len(returns) else None}

MODEL_COLUMNS={
    "ETF_MARKET":"macro_market_selected",
    "ETF_MARKET_WITH_PEERS_ONLY":"macro_peer_only_selected",
    "ETF_MARKET_WITH_SYMBOL_ONLY":"macro_symbol_only_selected",
    "ETF_MARKET_WITH_PEERS_AND_SYMBOL":"macro_peer_selected",
}
def evaluate(pred,placebo_draws=1000,bootstrap_draws=5000,seed=20261111):
    d=prepare(pred)
    rows=[];annual=[]
    for model,col in MODEL_COLUMNS.items():
        for name,cost in ADDITIONAL_COST.items():
            rows.append({"model":model,"roundtrip":name,**_measure(d,col,cost)})
        for year,g in d.groupby("year"):
            annual.append({"model":model,"year":int(year),**_measure(g,col,0)})
    costs=pd.DataFrame(rows);years=pd.DataFrame(annual)
    outcome={}
    if placebo_draws>=100:
        for model,col in MODEL_COLUMNS.items():
            outcome[model]=_random_retention(d,col,placebo_draws,seed)
    yearly=[]
    for year,g in d.groupby("year"):
        ref=_measure(g,"macro_market_selected",0)["net_per_opportunity"]
        sym=_measure(g,"macro_symbol_only_selected",0)["net_per_opportunity"]
        peer=_measure(g,"macro_peer_only_selected",0)["net_per_opportunity"]
        both=_measure(g,"macro_peer_selected",0)["net_per_opportunity"]
        yearly.append({"year":int(year),"n":len(g),
            "macro_market":ref,"peer_only_increment":peer-ref,
            "symbol_only_increment":sym-ref,"peer_and_symbol_increment":both-ref})
    yy=pd.DataFrame(yearly)
    # Cluster by YEAR rather than independently re-sampling same-day correlated
    # stock events. 5 clusters are too few for conventional inferential CI.
    rng=np.random.default_rng(seed+17)
    ix=rng.integers(0,len(yy),size=(bootstrap_draws,len(yy)))
    weight=yy.n.to_numpy(dtype=float)
    numerators=(yy.peer_and_symbol_increment*weight).to_numpy()[ix].sum(axis=1)
    denom=weight[ix].sum(axis=1)
    bootstrap=(numerators/denom)
    distinct_dates=d.date.nunique()
    max_simultaneous=int(d.groupby("date").size().max())
    repeated_date_count=int((d.groupby("date").size()>1).sum())
    peer_by_year={int(y):int(g.peer_available.sum()) for y,g in d.groupby("year")}
    macro=_measure(d,"macro_market_selected",0)
    both=_measure(d,"macro_peer_selected",0)
    report={
      "status":"HOLD_NO_INDEPENDENT_PEER_OR_MACRO_ALPHA",
      "n_opportunities":len(d),"unique_signal_dates":distinct_dates,
      "multi_stock_signal_dates":repeated_date_count,
      "maximum_signals_one_date":max_simultaneous,
      "peer_scored_events_by_year":peer_by_year,
      "peer_usable_2025_2026":peer_by_year.get(2025,0)+peer_by_year.get(2026,0),
      "macro_only_net_per_opportunity":macro["net_per_opportunity"],
      "peer_symbol_net_per_opportunity":both["net_per_opportunity"],
      "peer_symbol_increment":both["net_per_opportunity"]-macro["net_per_opportunity"],
      "placebo":outcome,
      "year_cluster_bootstrap":{
          "n_years":len(yy),"n_draws":bootstrap_draws,
          "peer_symbol_increment_95pct_lower":float(np.quantile(bootstrap,.025)),
          "peer_symbol_increment_95pct_upper":float(np.quantile(bootstrap,.975)),
          "sign_positive_fraction":float((bootstrap>0).mean()),
          "independent_significance":False},
      "macro_pnl_sensitive_to_cost":True,
      "warning":"The same fixed strategy hypotheses and years were repeatedly inspected.",
      "no_live_promotion":True,
      "promotion_allowed":False
    }
    return d,costs,years,yy,report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pred",default="results/regime_countertrend/peer_macro_v4/probabilities.csv")
    parser.add_argument("--out",default="results/regime_countertrend/peer_macro_v4/stress")
    args=parser.parse_args()
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    pred=pd.read_csv(args.pred)
    annotated,costs,annual,increment,report=evaluate(pred)
    annotated.to_csv(root/"separate_peer_and_symbol_masks.csv",index=False)
    costs.to_csv(root/"costs_20_40_80bp.csv",index=False)
    annual.to_csv(root/"annual_reliability.csv",index=False)
    increment.to_csv(root/"annual_increment.csv",index=False)
    (root/"decision.json").write_text(json.dumps(report,indent=2))
    print("PEER_MACRO_V4_STRESS",json.dumps({
      "status":report["status"],"peer_2025_2026":report["peer_usable_2025_2026"],
      "mean_macro":report["macro_only_net_per_opportunity"],
      "mean_peer_symbol":report["peer_symbol_net_per_opportunity"],
      "year_bootstrap":report["year_cluster_bootstrap"],
      "models":costs[costs.roundtrip=="20bp"].to_dict("records"),
      "promotion_allowed":False}))
