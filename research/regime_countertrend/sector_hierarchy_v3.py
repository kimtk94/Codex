"""Industry-by-stock latent-factor research, no LIVE trading.

One common feature contract for every stock (QQQ=benchmark, 'qld'=target alias).
Two distinct grouping axes: 20 indicators -> correlated factors; stocks ->
static researched industry cohorts + independently measured return correlations.
Supervisor = global model, then industry peer and symbol models where supported.
Every fit is earlier-year only; annual OOS is previously explored and NOT untouched.
"""
import argparse
import json
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from .feature_coverage_v3 import FullCoverageFactorTransformer
from .correlated_factor_model import FEATURES,feature_frame
from .robust_walkforward import simulate
from .sector_price_sources_v3 import manifest_load

MIN_GLOBAL=80
MIN_GROUP=40
MIN_SYMBOL=26
C=0.25
THRESHOLD=0.55
STOCK_GROUP_WEIGHT=0.2
INDUSTRY_GROUP_WEIGHT=0.3
MAX_HOLD_DAYS=4

def make_pair(target,benchmark,symbol):
    t=target.rename(columns={k:f"{k}_qld" for k in ("open","high","low","close","volume")})
    b=benchmark.rename(columns={k:f"{k}_qqq" for k in ("open","high","low","close","volume")})
    df=t[["date",*["%s_qld"%k for k in ("open","high","low","close","volume")]]].merge(
        b[["date",*["%s_qqq"%k for k in ("open","high","low","close","volume")]]],
        on="date",validate="one_to_one",how="inner")
    df=df.rename(columns={"date":"date_ny"}).sort_values("date_ny").reset_index(drop=True)
    if len(df)<180 or df.date_ny.duplicated().any():
        raise ValueError(f"{symbol}: insufficient paired daily data")
    return df

def stock_proxy(panel,symbol,industry):
    # Do not merge stock labels across symbols before computing each stock's
    # forward price path, and use the exact same signal-day indicator contract.
    indicators=feature_frame(panel)
    q60=panel.close_qqq.pct_change(60)
    ret5=panel.close_qld.pct_change(5)
    events=[]
    last_event={}
    for i in range(65,len(panel)-MAX_HOLD_DAYS):
        if pd.isna(q60.iloc[i]) or pd.isna(ret5.iloc[i]):continue
        market="UP" if q60.iloc[i]>=.08 else ("DOWN" if q60.iloc[i]<=-.08 else "SIDE")
        if market=="UP" and ret5.iloc[i]<=-.03:event="UP_DIP"
        elif market=="DOWN" and ret5.iloc[i]>=.03:event="DOWN_RALLY"
        elif market=="SIDE" and ret5.iloc[i]<=-.03:event="SIDE_DIP"
        else:continue
        # Event cooldown per symbol and event; not a realized trading position constraint.
        if i-last_event.get(event,-1000)<5:continue
        last_event[event]=i
        f=indicators.iloc[i]
        if not np.isfinite(f[list(FEATURES)].to_numpy(dtype=float)).all():
            continue
        outcome=simulate(panel,i,"STOP_FIRST",roundtrip_bps=20,hold_days=4)
        row={"date":panel.iloc[i].date_ny,"year":int(str(panel.iloc[i].date_ny)[:4]),
             "symbol":symbol,"industry":industry,"event":event,
             "net_20bp":outcome["net"],"exit_date":outcome["exit_date"],
             "gap_exit":outcome["gap"],"ambiguous_bar":outcome["ambiguity"],
             "outcome":outcome["outcome"],"win":int(outcome["net"]>0)}
        row.update({x:float(f[x]) for x in FEATURES})
        events.append(row)
    return pd.DataFrame(events)

def panel_from_sources(manifest,root):
    folder=Path(root)
    failures=[];prices={};events=[];history=[]
    bench=folder/"QQQ.csv"
    if not bench.is_file():
        raise ValueError("QQQ benchmark unavailable")
    benchmark=pd.read_csv(bench)
    for a in manifest["universe"]:
        if not a["model_eligible"]:continue
        symbol=a["symbol"]
        p=folder/f"{symbol}.csv"
        if not p.is_file():
            failures.append({"symbol":symbol,"status":"HOLD_NO_VALIDATED_PRICE_FILE"})
            continue
        try:
            daily=pd.read_csv(p)
            pair=make_pair(daily,benchmark,symbol)
            features=feature_frame(pair)
            features["date_ny"]=pair.date_ny
            features["symbol"]=symbol
            history.append(features)
            proxies=stock_proxy(pair,symbol,a["industry"])
            if not proxies.empty:events.append(proxies)
            prices[symbol]=daily
        except Exception as exc:
            failures.append({"symbol":symbol,"status":"HOLD_FEATURE_OR_EVENT_FAILURE",
                             "type":type(exc).__name__,"reason":str(exc)[:130]})
    event_panel=pd.concat(events,ignore_index=True) if events else pd.DataFrame()
    features_panel=pd.concat(history,ignore_index=True) if history else pd.DataFrame()
    if len(event_panel) and event_panel.duplicated(["symbol","date"]).any():
        raise ValueError("duplicated symbol/signal")
    return prices,features_panel,event_panel,failures

def stock_correlation_report(prices,manifest,year_cutoff="2025-01-01"):
    # Stock clusters are observed on PAST DAILY RETURNS, not on price levels.
    stock=[r for r in manifest["universe"] if r["model_eligible"] and r["symbol"] in prices]
    d={a["symbol"]:pd.Series(prices[a["symbol"]].close.pct_change().to_numpy(),
            index=prices[a["symbol"]].date.astype(str)) for a in stock}
    frame=pd.DataFrame(d).sort_index()
    frame=frame[frame.index<year_cutoff]
    rows=[]
    for i,a in enumerate(stock):
        for b in stock[i+1:]:
            x=frame[[a["symbol"],b["symbol"]]].dropna()
            r=float(x.iloc[:,0].corr(x.iloc[:,1])) if len(x)>=126 else None
            rows.append({
                "symbol_a":a["symbol"],"symbol_b":b["symbol"],
                "industry_a":a["industry"],"industry_b":b["industry"],
                "same_industry":a["industry"]==b["industry"],
                "training_overlap":len(x),"corr_daily_return":r,
                "corr_cluster_edge":bool(r is not None and r>=.60),
                "train_cutoff":year_cutoff})
    return pd.DataFrame(rows)

def _eligible(train,nmin,klass=10):
    return (len(train)>=nmin and train.win.nunique()==2 and
            min(int(train.win.sum()),int((1-train.win).sum()))>=klass)

def _balanced_weights(df):
    per=df.symbol.value_counts()
    w=df.symbol.map(lambda s:1/np.sqrt(per[s])).to_numpy(dtype=float)
    return w/w.mean()

def _fit_supervisor(df,x):
    clf=LogisticRegression(C=C,max_iter=1500)
    clf.fit(x,df.win,sample_weight=_balanced_weights(df))
    return clf

def _input_latent(transformer,frame):
    vals=transformer.transform(frame)
    return np.column_stack([
        vals,(frame.event=="DOWN_RALLY").astype(int).to_numpy(),
        (frame.event=="SIDE_DIP").astype(int).to_numpy()
    ])

def run_hierarchy(features,events,manifest,first_year=2022):
    if events.empty or features.empty:
        return pd.DataFrame(),pd.DataFrame(),{"status":"HOLD_NO_PROXY_EVENTS","promotion_allowed":False}
    selected=[a for a in manifest["universe"] if a["model_eligible"]]
    members=Counter(a["industry"] for a in selected)
    preds=[];fits=[]
    for year in sorted(y for y in events.year.unique() if y>=first_year):
        cutoff=f"{year}-01-01"
        training=events[(events.year<year)&(events.exit_date<cutoff)].copy()
        test=events[events.year==year].copy()
        if not len(test):continue
        if not _eligible(training,MIN_GLOBAL,15):
            fits.append({"year":year,"status":"HOLD_INSUFFICIENT_GLOBAL_TRAINING",
                         "training_events":len(training),"tested_events":len(test)})
            continue
        history=features[features.date_ny<cutoff].dropna(subset=list(FEATURES)).copy()
        transformer=FullCoverageFactorTransformer().fit(history)
        xt=_input_latent(transformer,training)
        xv=_input_latent(transformer,test)
        market=_fit_supervisor(training,xt)
        global_prob=market.predict_proba(xv)[:,1]
        p_industry=np.full(len(test),np.nan)
        p_symbol=np.full(len(test),np.nan)
        context={"n_eligible_industry":0,"n_eligible_symbol":0}
        for industry in test.industry.unique():
            if members[industry]<2:continue
            a=training[training.industry==industry]
            if not _eligible(a,MIN_GROUP,8) or a.symbol.nunique()<2:continue
            industry_model=_fit_supervisor(a,_input_latent(transformer,a))
            mask=test.industry==industry
            p_industry[mask]=industry_model.predict_proba(xv[mask.to_numpy()])[:,1]
            context["n_eligible_industry"]+=1
        for sym in test.symbol.unique():
            a=training[training.symbol==sym]
            if not _eligible(a,MIN_SYMBOL,6):continue
            symbol_model=_fit_supervisor(a,_input_latent(transformer,a))
            mask=test.symbol==sym
            p_symbol[mask]=symbol_model.predict_proba(xv[mask.to_numpy()])[:,1]
            context["n_eligible_symbol"]+=1
        # Fixed, preregistered shrinkage toward the global pooled model;
        # unavailable peer/symbol channels transfer their weight to global.
        industry_available=np.isfinite(p_industry)
        stock_available=np.isfinite(p_symbol)
        final=((1-STOCK_GROUP_WEIGHT*stock_available.astype(float)-
                INDUSTRY_GROUP_WEIGHT*industry_available.astype(float))*global_prob +
               INDUSTRY_GROUP_WEIGHT*np.nan_to_num(p_industry,nan=0)+
               STOCK_GROUP_WEIGHT*np.nan_to_num(p_symbol,nan=0))
        if not np.isfinite(final).all():raise ValueError("nonfinite hierarchy output")
        for i,(_,r) in enumerate(test.iterrows()):
            preds.append({"year":year,"date":r.date,"symbol":r.symbol,
                "industry":r.industry,"event":r.event,"net_20bp":r.net_20bp,
                "win":r.win,"global_probability":float(global_prob[i]),
                "industry_probability":float(p_industry[i]) if industry_available[i] else None,
                "symbol_probability":float(p_symbol[i]) if stock_available[i] else None,
                "hierarchical_probability":float(final[i]),
                "global_selected":bool(global_prob[i]>=THRESHOLD),
                "hierarchical_selected":bool(final[i]>=THRESHOLD),
                "industry_model_available":bool(industry_available[i]),
                "symbol_model_available":bool(stock_available[i]),
                "n_latent_factors":len(transformer.factor_names),
                "n_input_features":len(transformer.used_features),
                "n_train_events":len(training)})
        fits.append({"year":year,"status":"FITTED","training_events":len(training),
             "tested_events":len(test),"input_feature_count":len(transformer.used_features),
             "latent_factors":len(transformer.factor_names),
             **context})
    pred=pd.DataFrame(preds)
    decisions=pd.DataFrame(fits)
    return pred,decisions,{
      "status":"HOLD_RESEARCH_SECTOR_HIERARCHY_NOT_LIVE",
      "evaluated_events":len(pred),
      "market_model":"all stocks trained on prior completed events only",
      "industry_model":"only manual industry cohorts >=2 stock members and enough prior event labels",
      "individual_model":"only when sufficient prior events for the same ticker",
      "hierarchy_weights":{"market_base":0.5,"industry":0.3,"symbol":0.2,
         "unavailable_weight":"redistributed_to_market"},
      "indicator_features_used":len(FEATURES),
      "risk_context":"QQQ market + ticker-dependent movement; ETFs only macro context",
      "SIDE_DIP":"exploratory SHADOW candidate not a LIVE order signal",
      "promotion_allowed":False,
      "limitations":[
        "Survivorship-biased handpicked research universe; some symbols were not listed early",
        "ETF history and stock returns use provider-adjusted OHLC, may change ex post",
        "Regime thresholds on high-volatility assets are not cross-stock risk calibrated",
        "All 2022-26 years have been investigated; not untouched independent evaluation",
        "Cross-symbol contemporaneous signals are correlated; no independent trade count",
        "Portfolio position limits, spread, brokerage fees and true 15m executions unverified"]
    }

def grouped_report(pred):
    if pred.empty:return pd.DataFrame(),pd.DataFrame()
    a=[]
    for (year,industry),df in pred.groupby(["year","industry"],sort=True):
        n=len(df)
        for model,col in (("BASELINE",None),("MARKET_FACTOR","global_selected"),
                          ("MARKET_INDUSTRY_SYMBOL","hierarchical_selected")):
            mask=np.ones(n,dtype=bool) if col is None else df[col].to_numpy(dtype=bool)
            kept=df.iloc[np.where(mask)[0]]
            a.append({"year":year,"industry":industry,"model":model,
                "opportunities":n,"taken":len(kept),
                "mean_net_per_opportunity":float(kept.net_20bp.sum()/n),
                "mean_selected":float(kept.net_20bp.mean()) if len(kept) else None,
                "losses":int((kept.net_20bp<0).sum())})
    industry=pd.DataFrame(a)
    asset=pred.groupby(["symbol","industry"],as_index=False).agg(
        events=("date","size"),first_signal=("date","min"),last_signal=("date","max"),
        industry_model_available=("industry_model_available","sum"),
        symbol_model_available=("symbol_model_available","sum"),
        loss_rate=("win",lambda x:float((x==0).mean())))
    return industry,asset

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",default="results/regime_countertrend/universe_v3_prices")
    p.add_argument("--manifest",default="research/regime_countertrend/universe_sector_v3.json")
    p.add_argument("--out",default="results/regime_countertrend/sector_v3")
    a=p.parse_args()
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    manifest=manifest_load(a.manifest)
    prices,daily,events,failed=panel_from_sources(manifest,a.source_dir)
    source_inventory={"status":"COVERAGE_ONLY" if not prices else "PARTIAL_OR_FULL",
       "stock_data_available":len(prices),"stock_target_expected":14,
       "per_symbol_holds":failed,
       "events_count":len(events),"feature_values_finite":not daily.empty and
           bool(np.isfinite(daily[list(FEATURES)].dropna().to_numpy()).all()),
       "promotion_allowed":False}
    if prices:
        corr=stock_correlation_report(prices,manifest)
        corr.to_csv(root/"stock_pair_return_correlations.csv",index=False)
    if events.empty:
        meta={"status":"HOLD_NO_VALIDATED_STOCK_SIGNALS","promotion_allowed":False}
    else:
        events.to_csv(root/"all_symbol_proxy_events.csv",index=False)
        pred,folds,meta=run_hierarchy(daily,events,manifest)
        folds.to_csv(root/"annual_training_coverage.csv",index=False)
        pred.to_csv(root/"pooled_industry_symbol_predictions.csv",index=False)
        industry,assets=grouped_report(pred)
        industry.to_csv(root/"industry_model_comparison.csv",index=False)
        assets.to_csv(root/"symbol_model_coverage.csv",index=False)
    meta["inventory"]=source_inventory
    (root/"status.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print("SECTOR_V3_STATUS",json.dumps({
      "status":meta["status"],"industry_years":int(len(folds)) if not events.empty else 0,
      "stock_sources":len(prices),"events":len(events),
      "evaluated":meta.get("evaluated_events",0),
      "industry_models":int(folds.n_eligible_industry.fillna(0).sum()) if not events.empty and "n_eligible_industry" in folds else 0,
      "symbol_models":int(folds.n_eligible_symbol.fillna(0).sum()) if not events.empty and "n_eligible_symbol" in folds else 0,
      "failed_stocks":failed,"promotion_allowed":False
    },ensure_ascii=False))
if __name__=="__main__":main()
