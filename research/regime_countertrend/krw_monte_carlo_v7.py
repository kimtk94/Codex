"""CFM V7 Monte Carlo risk review of the already-studied V6 KRW cash equity paths.

Synchronous stationary-block resampling keeps same-day cross-asset co-movement
and multiday market/FX shocks. Resample DAILY PORTFOLIO KRW marks, not iid
trades; this is a path-sensitivity test, NOT recalculated order executions.
The historical period and parameter choices have been repeatedly viewed.
No model retraining, no live trades, no real broker FX statements.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

CAPITAL_KRW=10_000_000
STOCK_FX_SPREAD_BPS=10
MODELS=("V4_ETF_MARKET","V5_KRW_REGIME_BASE")
POLICIES=("USD_RETAIN","EACH_SALE_CONVERT_TO_KRW")
ETF_BENCHMARKS=("SPY","QQQ","IWM","SMH","GLD")
BLOCK_LENGTHS=(5,20,60)
HORIZONS=(252,"observed_days")
SIMULATIONS=2000
RNG_SEED=20261115
BATCH=125

def load_joint_equity(folder,initial=CAPITAL_KRW):
    """Require exact date alignment and matching policy records, no forward fill."""
    folder=Path(folder)
    curves={}
    exposure=[]
    model_refs={}
    for model in MODELS:
        for policy in POLICIES:
            key=f"{model}__{policy}"
            path=folder/f"{key}__10bps_equity.csv"
            if not path.is_file():raise ValueError("missing V6 10bp policy curve "+key)
            frame=pd.read_csv(path)
            must={"date","equity_krw","fx_rate","cash_usd","cash_krw",
                  "position_mark_usd","open_positions"}
            if not must.issubset(frame):raise ValueError("missing risk cash path fields")
            if (frame.date.duplicated().any() or not frame.date.is_monotonic_increasing
                    or len(frame)<252):
                raise ValueError("invalid historical cash series "+key)
            if (frame.equity_krw<=0).any():
                raise ValueError("invalid synthetic account equity <=0")
            curves[key]=frame
            reference=curves[f"{MODELS[0]}__{POLICIES[0]}"]
            if not frame.date.reset_index(drop=True).equals(
                    reference.date.reset_index(drop=True)):
                raise ValueError("account daily paths use different dates")
            if not np.allclose(frame.fx_rate,reference.fx_rate,atol=1e-8,rtol=0):
                raise ValueError("cash models use different FX sources")
            exposed=((frame.cash_usd+frame.position_mark_usd)*frame.fx_rate/
                      frame.equity_krw)
            if not np.isfinite(exposed).all() or not exposed.between(-1e-7,1.0000001).all():
                raise ValueError("invalid FX exposure, leverage or negative cash")
            exposure.append({"asset":key,"average_usd_exposure":float(exposed.mean()),
                "median_usd_exposure":float(exposed.median()),
                "last_usd_exposure":float(exposed.iloc[-1])})
    baseline=pd.DataFrame({
        "date":curves[f"{MODELS[0]}__{POLICIES[0]}"].date.astype(str)})
    for key,frame in curves.items():
        baseline[key]=frame.equity_krw.to_numpy(float)
        model_refs[key]=float(frame.equity_krw.iloc[-1]/initial-1)
    for sym in ETF_BENCHMARKS:
        path=folder/f"passive_{sym}_equity_krw.csv"
        if not path.is_file():raise ValueError("missing ETF benchmark "+sym)
        v=pd.read_csv(path)
        if not v.date.reset_index(drop=True).equals(baseline.date):
            raise ValueError("ETF benchmark must align to same market days")
        baseline[sym]=v.equity_krw.to_numpy(float)
    reference=curves[f"{MODELS[0]}__{POLICIES[0]}"]
    fx_rate=reference.fx_rate.to_numpy(float)
    baseline["USD_CASH_ONLY"]=initial*fx_rate/(fx_rate[0]*
                                           (1+STOCK_FX_SPREAD_BPS/10000))
    baseline["KRW_CASH_ONLY"]=float(initial)
    fields=list(baseline.columns[1:])
    values=baseline[fields].to_numpy(float)
    if not np.isfinite(values).all() or (values<=0).any():
        raise ValueError("benchmark portfolio marks must be positive and finite")
    policy=folder/"policy_comparison.csv"
    if not policy.is_file():raise ValueError("missing policy cost evidence")
    actual=pd.read_csv(policy)
    for key,expected in model_refs.items():
        model,holding=key.split("__")
        records=actual[(actual.model==model)&(actual.cash_policy==holding)&
                       (actual.spread_per_conversion_leg_bps==10)]
        if len(records)!=1:raise ValueError("missing/duplicate policy scenario "+key)
        v=float(records.initial_to_final_krw_return_pct.iloc[0])/100
        if not np.isclose(v,expected,atol=1e-8,rtol=0):
            raise ValueError("cash policy equity time series differs from report")
        if records.portfolio_status.iloc[0]!="SYNTHETIC_NOT_BROKER_RECONCILED":
            raise ValueError("no real brokerage evidence authorized")
    initial_friction=values[0,:]/initial
    daily=values[1:,:]/values[:-1,:]-1
    if (daily<=-1).any() or not np.isfinite(daily).all():
        raise ValueError("daily return lost positive wealth")
    recomputed=initial_friction*np.prod(1+daily,axis=0)
    expected=values[-1,:]/initial
    if not np.allclose(recomputed,expected,atol=1e-9,rtol=1e-9):
        raise ValueError("return reconstruction error")
    return baseline,fields,daily,initial_friction,exposure,actual

def _stationary_indices(n_periods,horizon,mean_block,simulations,rng):
    """Shared synthetic trading-day indices for all portfolio and ETF columns."""
    if not 1<=mean_block<=n_periods or horizon<2 or simulations<1:
        raise ValueError("invalid bootstrap geometry")
    begins=rng.integers(0,n_periods,size=(simulations,horizon),dtype=np.int32)
    restart=rng.random((simulations,horizon)) < (1.0/mean_block)
    out=np.empty_like(begins)
    out[:,0]=begins[:,0]
    for t in range(1,horizon):
        out[:,t]=np.where(restart[:,t],begins[:,t],
                          (out[:,t-1]+1)%n_periods)
    return out

def _outcome_statistics(paths,drawdowns,names,initial_friction):
    if paths.ndim!=2 or drawdowns.shape!=paths.shape:
        raise ValueError("invalid monte carlo terminal/drawdown arrays")
    if not np.isfinite(paths).all() or not np.isfinite(drawdowns).all():
        raise ValueError("nonfinite bootstrap outcomes")
    target_index={name:i for i,name in enumerate(names)}
    rows=[]
    for j,name in enumerate(names):
        x=paths[:,j]
        m=drawdowns[:,j]
        q5=float(np.quantile(x,.05))
        tail=x[x<=q5]
        row={"asset":name,"simulations":len(x),
             "median_total_return_pct":float(np.median(x)*100),
             "p05_total_return_pct":q5*100,
             "p95_total_return_pct":float(np.quantile(x,.95)*100),
             "expected_total_return_pct":float(x.mean()*100),
             "cvar05_total_return_pct":float(tail.mean()*100),
             "p_terminal_loss":float((x<0).mean()),
             "p_loss_20pct_or_more":float((x<=-.20).mean()),
             "p_max_drawdown_below_minus_20pct":float((m<=-.20).mean()),
             "p_max_drawdown_below_minus_35pct":float((m<=-.35).mean()),
             "median_mdd_pct":float(np.median(m)*100),
             "initial_friction_pct":float((initial_friction[j]-1)*100)}
        if name.startswith("V4_") or name.startswith("V5_"):
            for comparator in ("QQQ","SPY","USD_CASH_ONLY"):
                k=target_index[comparator]
                relative=x-paths[:,k]
                row[f"p_underperform_{comparator}"]=float((relative<0).mean())
                row[f"p_beat_{comparator}"]=float((relative>0).mean())
                row[f"median_excess_vs_{comparator}_pct_points"]=float(
                    np.median(relative)*100)
        rows.append(row)
    return rows

def simulate_joint_blocks(daily,first,fields,lengths=BLOCK_LENGTHS,
                          horizons=HORIZONS,n_simulations=SIMULATIONS,
                          batch=BATCH,seed=RNG_SEED):
    if daily.ndim!=2 or len(fields)!=daily.shape[1]:
        raise ValueError("model/benchmark return matrix invalid")
    if min(n_simulations,batch)<1:
        raise ValueError("bad Monte Carlo replication count")
    if "QQQ" not in fields or "SPY" not in fields or "USD_CASH_ONLY" not in fields:
        raise ValueError("required KRW benchmark controls missing")
    rng=np.random.default_rng(seed)
    outputs=[]
    for horizon in horizons:
        steps=len(daily) if horizon=="observed_days" else int(horizon)
        if steps<20 or steps>5*len(daily):
            raise ValueError("invalid synthetic horizon")
        for block in lengths:
            end_returns=[]
            mdd=[]
            for start in range(0,n_simulations,batch):
                n=min(batch,n_simulations-start)
                idx=_stationary_indices(len(daily),steps,int(block),n,rng)
                picked=daily[idx]
                wealth=np.cumprod(1+picked,axis=1)*first[np.newaxis,np.newaxis,:]
                if not np.isfinite(wealth).all():
                    raise ValueError("bootstrap overflow")
                # Include initial KRW1 mark (before initial fee) as a peak.
                max_equity=np.maximum.accumulate(
                    np.concatenate([np.ones((n,1,len(fields))),wealth],axis=1),axis=1)[:,1:,:]
                dd=(wealth/max_equity-1).min(axis=1)
                end_returns.append(wealth[:,-1,:]-1)
                mdd.append(dd)
            end_returns=np.concatenate(end_returns,axis=0)
            mdd=np.concatenate(mdd,axis=0)
            stats=_outcome_statistics(end_returns,mdd,fields,first)
            for row in stats:
                outputs.append({"mean_block_trading_days":int(block),
                    "horizon_trading_days":int(steps),"horizon_name":str(horizon),
                    "sampling_method":"SYNCHRONOUS_STATIONARY_BLOCK",
                    **row})
    return pd.DataFrame(outputs)

def run_mc(root,output,n_simulations=SIMULATIONS,seed=RNG_SEED):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source_root=Path(root)
    equity,fields,daily,first,exposures,policies=load_joint_equity(source_root)
    required=[
        f"{model}__{policy}__10bps_equity.csv"
        for model in MODELS for policy in POLICIES
    ] + [
        f"passive_{sym}_equity_krw.csv" for sym in ETF_BENCHMARKS
    ] + ["policy_comparison.csv"]
    input_sha256={name:hashlib.sha256(
        (source_root/name).read_bytes()).hexdigest() for name in required}
    (output/"input_sha256.json").write_text(
        json.dumps(input_sha256,indent=2,sort_keys=True))
    vintage_file=source_root.parent/"vintage_v6"/"decision.json"
    vintage_status=(json.loads(vintage_file.read_text()).get("status")
                    if vintage_file.exists() else "SOURCE_VINTAGE_NOT_ATTESTED")
    output_stats=simulate_joint_blocks(daily,first,fields,
        n_simulations=n_simulations,seed=seed)
    output_stats.to_csv(output/"block_monte_carlo_krw_risk.csv",index=False)
    pd.DataFrame(exposures).to_csv(output/"usd_exposure_by_cash_policy.csv",index=False)
    fixed=policies.copy()
    fixed.to_csv(output/"deterministic_fx_cost_0_10_25bps.csv",index=False)
    # Historical terminal return and EOD drawdown are descriptive, not forecasts.
    hist=[]
    for name in fields:
        x=equity[name].to_numpy(float)
        dd=x/np.maximum.accumulate(np.r_[CAPITAL_KRW,x])[1:]-1
        hist.append({"asset":name,"observed_total_return_pct":float((x[-1]/CAPITAL_KRW-1)*100),
                     "observed_eod_mdd_pct":float(dd.min()*100),
                     "observed_days":len(x),"last_date":str(equity.date.iloc[-1])})
    pd.DataFrame(hist).to_csv(output/"historical_portfolio_outcome_summary.csv",index=False)
    result={"status":"HOLD_MONTE_CARLO_HISTORICAL_PROXY_ONLY",
       "model":"CFM_V6_KRW_PORTFOLIO_BOOTSTRAP_NOT_V7_PROSPECTIVE",
       "historical_source":"V6 synthetic daily equity curves/actual 10bp FX-spread scenario",
       "starts":str(equity.date.iloc[0]),"ends":str(equity.date.iloc[-1]),
       "historical_daily_changes":len(daily),
       "historical_source_vintage_status":vintage_status,
       "source_immutable_artifact_run":os.environ.get(
           "KALMAN_MONTE_CARLO_SOURCE_RUN_ID","UNSPECIFIED_LOCAL_SOURCE"),
       "input_sha256":input_sha256,
       "input_files_count":len(input_sha256),
       "joint_curves":list(fields),
       "simulation_paths_per_horizon_and_block":n_simulations,
       "horizons_trading_days":[252,len(daily)],
       "mean_block_lengths_trading_days":list(BLOCK_LENGTHS),
       "replicable_rng_seed":seed,
       "cost_scenarios_bps":["0","10","25"],
       "cost_scenarios_note":"0/10/25bp are deterministic V6 cash policy results; Monte Carlo resamples 10bp account equity curves only.",
       "fx_method":"Historical USDKRW effects are jointly resampled in same-day portfolio and passive USD cash marks; not independently random FX jumps.",
       "uncertainty_interpretation":"Bootstrap conditional on a repeatedly explored, retrospectively adjusted, non-executable OHLC proxy; not calibrated future probabilities.",
       "conditional_on_policy_position_sizing":True,
       "joint_asset_day_correlation_retained_within_blocks":True,
       "entry_order_fills_not_reexecuted":True,
       "live_broker_reconciliation":False,
       "independent_holdout_available":False,
       "v7_frozen_forward_model_performance_available":False,
       "risk_gate":"HOLD_NO_PROSPECTIVE_PROFITABILITY_EVIDENCE",
       "selection_bias":"V4/V5 researched on the same historical source; Monte Carlo does not remove model-selection bias",
       "promotion_allowed":False}
    (output/"decision.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    summary=output_stats[
      (output_stats.horizon_trading_days==252)&
      (output_stats.mean_block_trading_days==20)&
      (output_stats.asset.isin([
          "V4_ETF_MARKET__USD_RETAIN",
          "V5_KRW_REGIME_BASE__USD_RETAIN",
          "QQQ","SPY","USD_CASH_ONLY"]))]
    important=[
        "asset","p_terminal_loss","p_max_drawdown_below_minus_20pct",
        "median_total_return_pct","p05_total_return_pct","p_underperform_QQQ"
    ]
    print("CFM_V7_KRW_MONTE_CARLO",json.dumps({
       "status":result["status"],
       "input_files_count":len(input_sha256),
       "source_vintage":vintage_status,
       "one_year_block20_summary":json.loads(summary[important].to_json(orient="records")),
       "promotion_allowed":False},ensure_ascii=False))
    return output_stats,result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cash-dir",default="results/regime_countertrend/krw_cash_v6")
    p.add_argument("--out",default="results/regime_countertrend/monte_carlo_v7")
    p.add_argument("--simulations",type=int,default=SIMULATIONS)
    p.add_argument("--seed",type=int,default=RNG_SEED)
    a=p.parse_args()
    run_mc(a.cash_dir,a.out,n_simulations=a.simulations,seed=a.seed)

if __name__=="__main__":
    main()
