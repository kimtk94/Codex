"""Concentration, downside and matched-retention placebo for the frozen QLD proxy.

Decisions were previously explored on the same historical data; placebo p-values
are descriptive conditional diagnostics, NOT independent significance tests.
No equity curve, CAGR, MDD, brokerage fills, or live strategy promotion.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

COST_COLUMNS=("net_20bp","net_40bp","net_80bp")
RNG_SEED=20261103

def annotated(events,walkforward):
    need={"year","date","event","net_20bp","net_40bp","net_80bp",
          "bestcase_net_20bp","was_ambiguous","was_gap"}
    if need-set(events):raise ValueError("missing event columns "+str(sorted(need-set(events))))
    e=events.copy()
    e["year"]=pd.to_numeric(e.year,errors="raise").astype(int)
    if e.date.duplicated().any():raise ValueError("duplicate signal dates")
    wf=walkforward.copy()
    w=wf[wf.label=="WALK_FORWARD_SELECTED"]
    b=wf[wf.label=="BASELINE"]
    if w.year.duplicated().any() or b.year.duplicated().any():
        raise ValueError("duplicate annual walk-forward rows")
    if set(w.year)!=set(b.year):raise ValueError("missing annual baseline")
    rules=dict(zip(w.year,w.rule))
    e=e[e.year.isin(rules)].copy()
    e["rule"]=e.year.map(rules)
    if any(r not in e.columns for r in rules.values()):
        raise ValueError("unknown chosen rule")
    e["selected"]=[bool(r[rule]) for _,r in e.iterrows() for rule in [r["rule"]]]
    for _,r in w.iterrows():
        part=e[e.year==r.year]
        if len(part)!=int(r.opportunities) or int(part.selected.sum())!=int(r.taken):
            raise ValueError("event-level selection disagrees with prior walk-forward")
    return e.sort_values(["year","date"]).reset_index(drop=True)

def group_summary(events):
    rows=[]
    for (year,event),g in events.groupby(["year","event"],sort=True):
        keep=g[g.selected]
        excluded=g[~g.selected]
        rows.append({
            "year":int(year),"event":event,
            "opportunities":len(g),"selected":len(keep),
            "negative_opportunities":int((g.net_20bp<0).sum()),
            "selected_negative":int((keep.net_20bp<0).sum()),
            "excluded_negative":int((excluded.net_20bp<0).sum()),
            "excluded_positive":int((excluded.net_20bp>=0).sum()),
            "baseline_mean":float(g.net_20bp.mean()),
            "selected_mean_per_opportunity":float(keep.net_20bp.sum()/len(g)),
            "improvement_per_opportunity":float(-excluded.net_20bp.sum()/len(g))
        })
    return pd.DataFrame(rows)

def matched_placebo(events,n_draws=10000,seed=RNG_SEED):
    if n_draws<100:raise ValueError("n_draws too low")
    rng=np.random.default_rng(seed)
    groups=[]
    for _,g in events.groupby(["year","event"],sort=True):
        values=g.net_20bp.to_numpy(dtype=float)
        n=int(g.selected.sum())
        groups.append((values,n))
    baseline=float(events.net_20bp.sum())
    observed=float(events.loc[events.selected,"net_20bp"].sum())
    simulations=np.zeros(n_draws,dtype=float)
    for vals,n in groups:
        if n==0:continue
        if n==len(vals):
            simulations+=vals.sum()
            continue
        # Restrict random baseline to the SAME year x signal regime and take count.
        for k in range(n_draws):
            simulations[k]+=rng.choice(vals,n,replace=False).sum()
    diff=(observed-baseline)/len(events)
    diff_null=(simulations-baseline)/len(events)
    return {
        "draws":int(n_draws),"seed":int(seed),
        "matched_within":"year_and_regime; fixed number of selected signals",
        "observed_improvement_per_opportunity":float(diff),
        "random_expected_improvement_per_opportunity":float(diff_null.mean()),
        "random_null_5pct":float(np.quantile(diff_null,.05)),
        "random_null_95pct":float(np.quantile(diff_null,.95)),
        "descriptive_one_sided_placebo_probability":float((1+(diff_null>=diff-1e-12).sum())/(n_draws+1)),
        "valid_independent_significance_test":False
    }

def year_cluster_uncertainty(events,n_draws=10000,seed=RNG_SEED+1):
    y=events.groupby("year",sort=True).apply(
        lambda g: pd.Series({"n":len(g),
           "delta":float(g.loc[g.selected,"net_20bp"].sum()-g.net_20bp.sum())}),
        include_groups=False)
    if len(y)<2:raise ValueError("need multiple years")
    rng=np.random.default_rng(seed)
    idx=rng.integers(0,len(y),size=(n_draws,len(y)))
    x=y.delta.to_numpy()[idx].sum(axis=1)/y.n.to_numpy()[idx].sum(axis=1)
    return {"resample_unit":"year","unique_years":len(y),"draws":n_draws,
        "bootstrap_95pct_lower":float(np.quantile(x,.025)),
        "bootstrap_95pct_upper":float(np.quantile(x,.975)),
        "positive_fraction":float((x>0).mean()),
        "note":"Only seven annual clusters; exploratory and not an independent CI."}

def risk_metrics(values):
    v=np.asarray(values,dtype=float)
    if not len(v):return {"n":0}
    loss=v[v<0]
    return {"n":len(v),"negative_count":int(len(loss)),
        "mean":float(v.mean()),"median":float(np.median(v)),
        "worst":float(v.min()),"p10":float(np.quantile(v,.1)),
        "mean_of_losses":float(loss.mean()) if len(loss) else None}

def audit(events,walkforward,n_draws=10000,seed=RNG_SEED):
    e=annotated(events,walkforward)
    group=group_summary(e)
    baseline=e.net_20bp.to_numpy()
    selected=e.loc[e.selected,"net_20bp"].to_numpy()
    by_regime=e.groupby("event").agg(n=("date","size"),
         n_2022=("year",lambda x:int((x==2022).sum())),
         n_2025_2026=("year",lambda x:int((x>=2025).sum())),
         mean_net=("net_20bp","mean"),
         median_net=("net_20bp","median"),
         loss_rate=("net_20bp",lambda x:float((x<0).mean()))).reset_index()
    by_regime["share_of_regime_in_2022"]=by_regime.n_2022/by_regime.n
    cost_rows=[]
    for col in COST_COLUMNS+("bestcase_net_20bp",):
        total=float(e[col].sum())
        filtered=float(e.loc[e.selected,col].sum())
        cost_rows.append({"return_source":col,"baseline_mean_per_opportunity":total/len(e),
           "selected_mean_per_opportunity":filtered/len(e),
           "improvement":(filtered-total)/len(e)})
    costs=pd.DataFrame(cost_rows)
    leave=[]
    for year in sorted(e.year.unique()):
        g=e[e.year!=year]
        base=float(g.net_20bp.sum()/len(g))
        selected_return=float(g.loc[g.selected,"net_20bp"].sum()/len(g))
        leave.append({"excluded_year":int(year),"n":len(g),
           "baseline_mean":base,"selected_mean":selected_return,
           "improvement":selected_return-base})
    loo=pd.DataFrame(leave)
    placebo=matched_placebo(e,n_draws,seed)
    ci=year_cluster_uncertainty(e,n_draws,seed+1)
    chosen=walkforward[walkforward.label=="WALK_FORWARD_SELECTED"]
    report={
        "status":"HOLD_UNVALIDATED_ALPHA",
        "all_research_only":True,"new_independent_holdout":False,
        "revisited_2025_2026":True,
        "n_opportunities":len(e),"selected_n":int(e.selected.sum()),
        "blocked_losers":int(((~e.selected)&(e.net_20bp<0)).sum()),
        "blocked_winners":int(((~e.selected)&(e.net_20bp>=0)).sum()),
        "risk_all":risk_metrics(baseline),
        "risk_selected":risk_metrics(selected),
        "gap_event_count":int(e.was_gap.sum()),
        "ambiguous_event_count":int(e.was_ambiguous.sum()),
        "placebo":placebo,"year_cluster_bootstrap":ci,
        "leave_one_year_out_positive":int((loo.improvement>0).sum()),
        "leave_one_year_out_total":int(len(loo)),
        "selected_zero_trade_years":[int(y) for y in chosen.loc[chosen.taken==0,"year"]],
        "approval_allowed":False,
        "limitations":[
            "Gap-aware daily OHLC proxy is not 15-minute executed PnL",
            "RSI and MACD rules have been explored on these very years; selection bias",
            "Matched-random placebo conditions on selection counts, not trading policy",
            "Year-level observations and trades are not independent",
            "Trade sums and per-opportunity averages are NOT portfolio total return",
            "No verified MDD, Sharpe, real costs, latency or slippage",
            "Do not promote any regime-specific rule on this evidence"
        ]}
    return group,by_regime,costs,loo,report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--events",required=True)
    p.add_argument("--walkforward",required=True)
    p.add_argument("--out",default="results/regime_countertrend/regime_stress")
    p.add_argument("--draws",type=int,default=10000)
    a=p.parse_args()
    g,r,c,l,report=audit(pd.read_csv(a.events),pd.read_csv(a.walkforward),a.draws)
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    for name,df in (("annual_regime.csv",g),("regime_concentration.csv",r),
                    ("cost_barrier_stress.csv",c),("leave_one_year_out.csv",l)):
        df.to_csv(dest/name,index=False)
    (dest/"decision.json").write_text(json.dumps(report,indent=2))
    print("REGIME_STRESS",json.dumps(report))
    print("REGIME_CONCENTRATION\n"+r.to_string(index=False))
    print("COST_AND_BARRIER\n"+c.to_string(index=False))
