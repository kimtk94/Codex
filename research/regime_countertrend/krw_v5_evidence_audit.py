"""KRW-account perspective: aligned V4/V5 ablation with year/sector/regime/FX flips.

Only descriptive retrospective analysis. Reused historical window, not untouched
holdout. FX quoted previous-date daily close is not an executed bank conversion.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

RETURNS={
 "USD": "usd_net_return",
 "KRW_MARK":"krw_mark_return",
 "KRW_FX_10BPS_EACH_SIDE":"krw_roundtrip_fx_10bps_each_side",
 "KRW_FX_25BPS_EACH_SIDE":"krw_roundtrip_fx_25bps_each_side"
}
V5_MODELS=(
    "FX_REGIME_BASE",
    "FX_REGIME_PLUS_LOCATION_VOLUME",
    "FX_REGIME_DETAIL_INTERACTIONS"
)

def check_coverage(v4,v5):
    key=["date","symbol","year"]
    if v4.duplicated(key).any():raise ValueError("duplicate V4 signal identity")
    if v5.duplicated(key+["model"]).any():raise ValueError("duplicate V5 model identity")
    if set(v5.model)!=set(V5_MODELS):raise ValueError("missing V5 model branch")
    a=v4[key].astype(str).agg("|".join,axis=1)
    if a.duplicated().any():raise ValueError("duplicate V4 keys")
    for model,g in v5.groupby("model"):
        b=g[key].astype(str).agg("|".join,axis=1)
        if set(a)!=set(b):raise ValueError(f"{model} cohort mismatch")
        if len(g)!=len(v4):raise ValueError("V5 cardinality changed")
    for field in ("usd_net_return","krw_mark_return",*list(RETURNS.values())[2:]):
        if field not in v4:raise ValueError("missing FX return")
        if not np.isfinite(v4[field]).all():raise ValueError("invalid V4 FX return")
    for date_col,ref_col in (("entry_date","entry_fx_reference_date"),
                             ("exit_date","exit_fx_reference_date")):
        if not (v4[ref_col].astype(str)<v4[date_col].astype(str)).all():
            raise ValueError("FX future date leakage")
    for age_col in ("entry_fx_age_calendar_days","exit_fx_age_calendar_days"):
        ages=pd.to_numeric(v4[age_col],errors="raise")
        if not ages.between(1,5).all():raise ValueError("FX stale or future")
    return len(v4)

def model_cohort(v4,v5):
    k=["date","symbol","year","industry","event"]
    masks={
      "BASELINE_USD_EVENTS":np.ones(len(v4),dtype=bool),
      "V4_ETF_MARKET_USD_TRAINED":v4.macro_market_selected.astype(bool).to_numpy(),
      "V4_ETF_PEER_SYMBOL_USD_TRAINED":v4.macro_peer_selected.astype(bool).to_numpy()
    }
    joined=[]
    for model,g in v5.groupby("model"):
        m=g[["date","symbol","year","model","selected",
             "krw_mark_return","net_20bp"]].rename(columns={
                 "krw_mark_return":"v5_krw",
                 "net_20bp":"v5_usd"})
        data=v4.merge(m,on=["date","symbol","year"],validate="one_to_one",
                      how="inner")
        if len(data)!=len(v4) or not np.allclose(data.v5_krw,data.krw_mark_return):
            raise ValueError("V5 price target mismatches V4 KRW")
        if not np.allclose(data.v5_usd,data.usd_net_return):
            raise ValueError("V5 price target mismatches V4 USD")
        joined.append((model,data.selected.astype(bool).to_numpy()))
    masks.update({model:mask for model,mask in joined})
    return masks

def metrics(v4,mask,model,cohort,group_by=None):
    n=len(v4)
    part=v4[mask]
    rows=[]
    for c,field in RETURNS.items():
        values=part[field].to_numpy(float)
        positive=values[values>0]
        negative=values[values<0]
        average_win=float(positive.mean()) if len(positive) else None
        average_loss=float(negative.mean()) if len(negative) else None
        breakeven=(abs(average_loss)/(average_win+abs(average_loss))
                   if average_win is not None and average_loss is not None else None)
        profit_factor=(float(positive.sum()/abs(negative.sum()))
                       if len(positive) and len(negative) else None)
        rows.append({
            "cohort":cohort,"model":model,"currency_scenario":c,
            "opportunities":n,"trades":len(part),
            "win_rate":float((values>0).mean()) if len(part) else None,
            "mean_per_selected":float(values.mean()) if len(part) else None,
            "mean_per_opportunity":float(values.sum()/n) if n else None,
            "negative_trades":int(len(negative)),
            "worst_trade":float(values.min()) if len(part) else None,
            "average_winner":average_win,"average_loser":average_loss,
            "break_even_win_rate_at_sample_payoff":breakeven,
            "payoff_ratio":float(average_win/abs(average_loss))
                if average_win is not None and average_loss is not None else None,
            "profit_factor":profit_factor
        })
    return rows

def audit(v4,v5):
    n=check_coverage(v4,v5)
    ordered=v4.sort_values(["date","symbol"]).reset_index(drop=True).copy()
    choices=model_cohort(ordered,v5)
    summary=[]
    for model,mask in choices.items():
        summary.extend(metrics(ordered,mask,model,"ALL"))
    for (year,industry,event),g in ordered.groupby(["year","industry","event"],sort=True):
        idx=g.index.to_numpy()
        for model,mask in choices.items():
            summary.extend(metrics(g,mask[idx],model,f"{year}|{industry}|{event}"))
    annual=[]
    for year,g in ordered.groupby("year",sort=True):
        idx=g.index.to_numpy()
        for model,mask in choices.items():
            p=g.loc[mask[idx]]
            annual.append({"year":int(year),"model":model,
                "n_opportunities":len(g),"selected":len(p),
                "krw_win_rate":float((p.krw_mark_return>0).mean()) if len(p) else None,
                "net_krw_per_opportunity":float(p.krw_mark_return.sum()/len(g)),
                "net_krw_10bp_per_opportunity":float(
                    p.krw_roundtrip_fx_10bps_each_side.sum()/len(g))})
    v4["usd_win"]=v4.usd_net_return>0
    v4["krw_win"]=v4.krw_mark_return>0
    flip_usd_win_krw_loss=int((v4.usd_win&~v4.krw_win).sum())
    flip_usd_loss_krw_win=int((~v4.usd_win&v4.krw_win).sum())
    by_regime=v4.groupby("event").agg(
        opportunities=("date","size"),
        usd_winners=("usd_win","sum"),
        krw_winners=("krw_win","sum"),
        usd_mean=("usd_net_return","mean"),
        krw_mean=("krw_mark_return","mean"),
        fx_mean=("fx_return","mean")).reset_index()
    details=v5.groupby(["year","model"],as_index=False).agg(
        trades=("selected","sum"),rows=("selected","size"),
        krw_wins=("krw_win",lambda x:int(x.sum())))
    report={
      "status":"HOLD_REVISITED_KRW_REGIME_DETAIL_ALPHA",
      "opportunities":n,"models":list(choices),
      "usd_win_krw_loss":flip_usd_win_krw_loss,
      "usd_loss_krw_win":flip_usd_loss_krw_win,
      "fx_mark_contribution_identity_valid":bool(np.allclose(
          v4.krw_mark_return,v4.usd_net_return+v4.fx_contribution+
          v4.interaction_contribution)),
      "source_fx_entry_precedes_trade":True,
      "source_fx_exit_precedes_trade":True,
      "fx_conversion_charged_every_trade":False,
      "roundtrip_fx_scenarios_only":True,
      "notes":[
          "USDKRW daily quote is KRW per USD; previous dated FX close, not execution-time fill",
          "When buying with KRW and existing USD cash, only shortfall may be converted",
          "A sell does not always involve immediate conversion back to KRW",
          "The 10/25 bps each-side scenarios are assumptions, not verified broker discounts",
          "The KRW Mark scenario is valuation of USD exposures in KRW, not settled account PnL",
          "Original V4 probabilities were USD-trained; V5 KRW-trained comparisons are in the same historical folds",
          "The 2022–2026 data was repeatedly examined; future untouched testing is still required",
          "Same-day stock opportunities are correlated and cannot be summed as independent account returns",
          "Price source is revised-adjusted daily OHLC not executable 15m or brokerage fills"
      ],
      "promotion_allowed":False
    }
    return pd.DataFrame(summary),pd.DataFrame(annual),by_regime,details,report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--v4",default="results/regime_countertrend/krw_fx_v5/v4_krw_trades_with_fx_attribution.csv")
    ap.add_argument("--v5",default="results/regime_countertrend/krw_detail_v5/yearly_krw_detail_predictions.csv")
    ap.add_argument("--out",default="results/regime_countertrend/krw_v5_audit")
    args=ap.parse_args()
    folder=Path(args.out);folder.mkdir(parents=True,exist_ok=True)
    v4=pd.read_csv(args.v4)
    v5=pd.read_csv(args.v5)
    totals,annual,regime,details,decision=audit(v4,v5)
    totals.to_csv(folder/"all_and_year_industry_regime.csv",index=False)
    annual.to_csv(folder/"model_krw_annual_reliability.csv",index=False)
    regime.to_csv(folder/"fx_regime_winning_swaps.csv",index=False)
    details.to_csv(folder/"detail_selection_by_year.csv",index=False)
    (folder/"decision.json").write_text(json.dumps(decision,indent=2,ensure_ascii=False))
    print("KRW_V5_AUDIT",json.dumps({
        "status":decision["status"],"opportunities":decision["opportunities"],
        "usd_positive_krw_negative":decision["usd_win_krw_loss"],
        "usd_negative_krw_positive":decision["usd_loss_krw_win"],
        "annual_krw_model_results":annual.to_dict("records"),
        "promotion_allowed":False},ensure_ascii=False))
if __name__=="__main__":main()
