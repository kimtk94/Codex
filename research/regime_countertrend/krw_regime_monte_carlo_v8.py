"""CFM V8: Regime-conditioned KRW Monte Carlo on a PINNED V6 cash vintage.

Condition a 252-session stress path on a PRIOR-CLOSE QQQ regime, and resample
one identical day-index vector across KRW strategies, passive ETFs and USD cash.
Within-state contiguous returns are kept in short blocks; state transitions
are intentionally suppressed. This is a counterfactual "persistent regime"
stress scenario, NOT a Markov probability forecast nor a fresh alpha test.
Do not retune historical rules or place LIVE orders.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .krw_monte_carlo_v7 import (
    CAPITAL_KRW, RNG_SEED, _outcome_statistics, load_joint_equity
)

SCENARIOS=("UP","DOWN","SIDE","HIGH_VOL","LOW_VOL","DOWN_HIGH_VOL")
MEAN_BLOCKS=(5,20,60)
HORIZON=252
SIMULATIONS=2000
BATCH=125
VOL_TRAIN_END="2021-12-31"
UP_TREND=.08
DOWN_TREND=-.08
MIN_ELIGIBLE_DAYS=80
MIN_DISTINCT_RUNS=8
MAX_SINGLE_YEAR_SHARE=.75

def previous_close_regimes(qqq,return_dates):
    """Classify trading day t ONLY with market closes available at t-1.

    Volatility threshold fitted using QQQ <=2021-12-31, before 2022 onward
    V6 portfolio evaluation. QQQ adjustments may be revised retrospectively.
    """
    if not {"date","close"}.issubset(qqq):
        raise ValueError("QQQ must include date and close")
    q=qqq[["date","close"]].copy().sort_values("date")
    if q.date.duplicated().any() or not q.date.is_monotonic_increasing:
        raise ValueError("QQQ duplicate/out-of-order trading dates")
    price=q.close.astype(float)
    if (price<=0).any() or not np.isfinite(price).all():
        raise ValueError("QQQ price invalid")
    returns=price.pct_change(fill_method=None)
    trend60=price.pct_change(60,fill_method=None)
    vol20=returns.rolling(20,min_periods=20).std()*np.sqrt(252)
    train=vol20[q.date<=VOL_TRAIN_END].dropna()
    if len(train)<252:
        raise ValueError("insufficient pre-2022 realized volatility training")
    threshold=float(train.quantile(.75))
    if not np.isfinite(threshold) or threshold<=0:
        raise ValueError("invalid fixed pre-2022 vol threshold")
    trend=np.select([trend60>=UP_TREND,trend60<=DOWN_TREND],
                    ["UP","DOWN"],default="SIDE")
    enriched=pd.DataFrame({
        "date":q.date.astype(str),
        "prior_close_date":q.date.shift(1).astype("string"),
        "prior_qqq_ret60":trend60.shift(1),
        "prior_qqq_vol20_ann":vol20.shift(1),
        "prior_trend":pd.Series(trend,index=q.index).shift(1),
        "prior_high_vol":(vol20.shift(1)>=threshold)})
    target=pd.DataFrame({"date":pd.Series(return_dates,dtype=str)})
    result=target.merge(enriched,on="date",how="left",validate="one_to_one")
    if len(result)!=len(target) or result.prior_trend.isna().any():
        raise ValueError("QQQ regime missing for a cash return date")
    if (result.prior_close_date.astype(str)>=result.date.astype(str)).any():
        raise ValueError("QQQ lookahead: source candle not strictly before return")
    if result[["prior_qqq_ret60","prior_qqq_vol20_ann"]].isna().any().any():
        raise ValueError("QQQ regime history missing after warmup")
    if not np.isfinite(result[["prior_qqq_ret60","prior_qqq_vol20_ann"]].to_numpy(float)).all():
        raise ValueError("QQQ regime values nonfinite")
    result["prior_high_vol"]=result.prior_high_vol.astype(bool)
    result["prior_down_high_vol"]=(
       result.prior_trend.eq("DOWN")&result.prior_high_vol)
    return result,{
       "up_threshold_60_session_return":UP_TREND,
       "down_threshold_60_session_return":DOWN_TREND,
       "volatility_lookback":20,
       "volatility_annualization":"sqrt(252)",
       "high_vol_cutoff":threshold,
       "volatility_quantile":.75,
       "volatility_cutoff_fitted_no_later_than":VOL_TRAIN_END,
       "regime_state_lag":1,
       "state_known_prior_to_return_day":True}

def scenario_mask(states,scenario):
    if scenario=="UP":return states.prior_trend.eq("UP").to_numpy(dtype=bool)
    if scenario=="DOWN":return states.prior_trend.eq("DOWN").to_numpy(dtype=bool)
    if scenario=="SIDE":return states.prior_trend.eq("SIDE").to_numpy(dtype=bool)
    if scenario=="HIGH_VOL":return states.prior_high_vol.to_numpy(dtype=bool)
    if scenario=="LOW_VOL":return ~states.prior_high_vol.to_numpy(dtype=bool)
    if scenario=="DOWN_HIGH_VOL":return states.prior_down_high_vol.to_numpy(dtype=bool)
    raise ValueError("unrecognized regime condition")

def _runs(mask):
    n=len(mask)
    start=mask & ~np.r_[False,mask[:-1]]
    ends=mask & ~np.r_[mask[1:],False]
    lengths=np.flatnonzero(ends)-np.flatnonzero(start)+1
    return int(start.sum()),int(lengths.max()) if len(lengths) else 0

def conditional_joint_indices(mask,horizon,mean_block,repetitions,rng):
    """Same indices for ALL assets; stop a sequential block at regime changes.

    A forced state-boundary restart does not count as a full L-day block.
    The realized effective run length is returned to prevent false claims.
    """
    mask=np.asarray(mask,dtype=bool)
    allowed=np.flatnonzero(mask)
    if len(allowed)==0 or horizon<2 or repetitions<1 or mean_block<1:
        raise ValueError("bad conditional bootstrap parameters")
    starts=rng.integers(0,len(allowed),size=(repetitions,horizon),dtype=np.int32)
    candidates=allowed[starts]
    state=np.empty((repetitions,horizon),dtype=np.int32)
    state[:,0]=candidates[:,0]
    total_restarts=repetitions
    boundary_forced=0
    for step in range(1,horizon):
        nxt=state[:,step-1]+1
        outside=nxt>=len(mask)
        clipped=np.minimum(nxt,len(mask)-1)
        outside|=~mask[clipped]
        scheduled=rng.random(repetitions)<(1.0/mean_block)
        restart=outside|scheduled
        state[:,step]=np.where(restart,candidates[:,step],nxt)
        total_restarts+=int(restart.sum())
        boundary_forced+=int((outside & ~scheduled).sum())
    if not mask[state].all():
        raise ValueError("conditional block escaped scenario Regime")
    effective=float(repetitions*horizon/total_restarts)
    return state,{
       "average_realized_block_sessions":effective,
       "forced_boundary_restart_fraction":float(boundary_forced/
             (repetitions*(horizon-1))),
       "total_blocks":int(total_restarts)}

def conditional_stress(daily,first,names,states,conditions=SCENARIOS,
                       lengths=MEAN_BLOCKS,n_simulations=SIMULATIONS,
                       horizon=HORIZON,batch=BATCH,seed=RNG_SEED):
    if daily.ndim!=2 or len(states)!=len(daily) or len(names)!=daily.shape[1]:
        raise ValueError("market conditional risk matrices unaligned")
    if not np.isfinite(daily).all() or (daily<=-1).any():
        raise ValueError("nonfinite or impossible daily portfolio return")
    if len(first)!=len(names) or not np.isfinite(first).all() or (first<=0).any():
        raise ValueError("invalid one-time initial FX friction")
    for name in ("QQQ","SPY","USD_CASH_ONLY"):
        if name not in names:raise ValueError("missing matched KRW risk benchmark "+name)
    if horizon<10 or n_simulations<1 or batch<1:
        raise ValueError("invalid risk geometry")
    rng=np.random.default_rng(seed)
    history=[];results=[];held=[]
    for scenario in conditions:
        mask=scenario_mask(states,scenario)
        count=int(mask.sum())
        runs,max_run=_runs(mask)
        years=states.loc[mask,"date"].str.slice(0,4).value_counts()
        majority=float(years.max()/count) if count else 1.
        sufficient=(count>=MIN_ELIGIBLE_DAYS and runs>=MIN_DISTINCT_RUNS)
        tag="HOLD_INSUFFICIENT_REGIME_HISTORY" if not sufficient else (
            "HOLD_SINGLE_YEAR_CONCENTRATION" if majority>MAX_SINGLE_YEAR_SHARE else
            "CONDITIONAL_RISK_DESCRIPTIVE_ONLY")
        coverage={"scenario":scenario,"sample_days":count,
            "share_of_historical_days":float(count/len(states)),
            "independent_contiguous_runs":runs,"longest_run_days":max_run,
            "largest_year_fraction":majority,
            "largest_year":str(years.idxmax()) if count else None,
            "year_counts":years.sort_index().astype(int).to_dict(),
            "risk_status":tag,"promotion_allowed":False}
        history.append(coverage)
        if not sufficient:
            held.append(scenario)
            continue
        for block in lengths:
            ends=[];minima=[];eff=[];forced=[]
            for start in range(0,n_simulations,batch):
                n=min(batch,n_simulations-start)
                idx,diag=conditional_joint_indices(mask,horizon,
                           int(block),n,rng)
                # A single index vector is simultaneously applied to every
                # stock strategy, passive ETF and KRW/USD cash benchmark.
                sampled=daily[idx]
                wealth=np.cumprod(1+sampled,axis=1)*first[None,None,:]
                if not np.isfinite(wealth).all():
                    raise ValueError("regime Monte Carlo wealth overflow")
                peaks=np.maximum.accumulate(np.concatenate([
                    np.ones((n,1,len(names))),wealth],axis=1),axis=1)[:,1:,:]
                minima.append((wealth/peaks-1).min(axis=1))
                ends.append(wealth[:,-1,:]-1)
                eff.append((n,diag["average_realized_block_sessions"]))
                forced.append((n,diag["forced_boundary_restart_fraction"]))
            stats=_outcome_statistics(
                np.concatenate(ends),np.concatenate(minima),names,first)
            total=sum(n for n,_ in eff)
            average_block=float(sum(n*v for n,v in eff)/total)
            forced_share=float(sum(n*v for n,v in forced)/total)
            for record in stats:
                results.append({
                    "scenario":scenario,
                    "requested_mean_block":int(block),
                    "effective_mean_block":average_block,
                    "forced_state_boundary_restart_fraction":forced_share,
                    "horizon_days":horizon,
                    "source_days":count,"source_runs":runs,
                    "largest_year_fraction":majority,
                    "risk_status":tag,
                    "sampling_method":"STATIONARY_BLOCK_TRUNCATED_AT_REGIME_BOUNDARY",
                    "conditional_full_path_in_requested_state":True,
                    **record})
    results_frame=pd.DataFrame(results) if results else pd.DataFrame(
        columns=["scenario","asset","requested_mean_block","p_terminal_loss",
                 "p_max_drawdown_below_minus_20pct"])
    return results_frame,pd.DataFrame(history),{
        "held_scenarios":held,"conditioned":len(history)-len(held),
        "reported":len(results)}

def run_regime_mc(cash_dir,qqq_file,out,
                  simulations=SIMULATIONS,seed=RNG_SEED):
    output=Path(out);output.mkdir(parents=True,exist_ok=True)
    source=Path(cash_dir)
    price_path=Path(qqq_file)
    if not price_path.is_file():raise ValueError("missing exact pinned QQQ source")
    qqq_bytes=price_path.read_bytes()
    qqq_sha=hashlib.sha256(qqq_bytes).hexdigest()
    equity,names,daily,first,exposures,policy=load_joint_equity(source)
    states,cutoffs=previous_close_regimes(
        pd.read_csv(price_path),equity.date.iloc[1:].astype(str))
    output_stats,coverage,meta=conditional_stress(
        daily,first,names,states,n_simulations=simulations,seed=seed)
    states.to_csv(output/"dated_prior_close_regime_labels.csv",index=False)
    coverage.to_csv(output/"regime_coverage_and_year_concentration.csv",index=False)
    output_stats.to_csv(output/"regime_conditional_krw_monte_carlo.csv",index=False)
    source_checksums={
        name:hashlib.sha256((source/name).read_bytes()).hexdigest()
        for name in ([f"{model}__{pol}__10bps_equity.csv"
             for model in ("V4_ETF_MARKET","V5_KRW_REGIME_BASE")
             for pol in ("USD_RETAIN","EACH_SALE_CONVERT_TO_KRW")]
             +[f"passive_{s}_equity_krw.csv" for s in
                 ("SPY","QQQ","IWM","SMH","GLD")]
             +["policy_comparison.csv"])}
    evidence={"status":"HOLD_REGIME_CONDITIONAL_HISTORICAL_STRESS_ONLY",
        "sourcing":"PINNED_2026_11_15_V6_KRW_CASH_AND_QQQ_CLOSE",
        "cash_source_files_sha256":source_checksums,
        "qqq_close_source_sha256":qqq_sha,
        "cash_daily_changes":len(daily),
        "conditional_scenarios":list(SCENARIOS),
        "scenario_sufficient_count":meta["conditioned"],
        "scenario_hold_count":len(meta["held_scenarios"]),
        "held_scenarios":meta["held_scenarios"],
        "simulations_per_scenario_block":simulations,
        "horizon_days":HORIZON,"requested_blocks":list(MEAN_BLOCKS),
        "rng_seed":seed,
        "pre_period_regime_thresholds":cutoffs,
        "coverage":coverage.to_dict("records"),
        "status_explanation":"Risk conditional on 2022–2026 synthetic cash curves; no trades rerun. Persistent-state scenarios intentionally suppress regime transitions.",
        "no_actual_broker_reconciliation":True,
        "not_independent_alpha_evidence":True,
        "potential_history_concentration":True,
        "same_day_stock_etf_fx_dependence_preserved":True,
        "promotion_allowed":False}
    (output/"decision.json").write_text(
        json.dumps(evidence,indent=2,ensure_ascii=False))
    headline=output_stats[
        (output_stats.requested_mean_block==20)&
        (output_stats.asset.isin(["V4_ETF_MARKET__USD_RETAIN",
                                  "V5_KRW_REGIME_BASE__USD_RETAIN",
                                  "QQQ"]))]
    if headline.empty:
        risk_headline=[]
    else:
        risk_headline=json.loads(headline[["scenario","asset",
            "p_terminal_loss","p_max_drawdown_below_minus_20pct",
            "p_underperform_QQQ","median_total_return_pct",
            "p05_total_return_pct"]].to_json(orient="records"))
    print("CFM_V8_REGIME_MC",json.dumps({
        "status":evidence["status"],
        "qqq_sha256":qqq_sha,
        "sample_days_by_regime":coverage[["scenario","sample_days",
                 "largest_year_fraction","risk_status"]].to_dict("records"),
        "one_year_block20":risk_headline,
        "promotion_allowed":False},ensure_ascii=False))
    return output_stats,coverage,evidence

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cash-dir",default="results/regime_countertrend/krw_cash_v6")
    p.add_argument("--qqq",default="results/regime_countertrend/universe_v3_prices/QQQ.csv")
    p.add_argument("--out",default="results/regime_countertrend/regime_mc_v8")
    p.add_argument("--simulations",type=int,default=SIMULATIONS)
    p.add_argument("--seed",type=int,default=RNG_SEED)
    a=p.parse_args()
    run_regime_mc(a.cash_dir,a.qqq,a.out,
                  simulations=a.simulations,seed=a.seed)

if __name__=="__main__":
    main()
