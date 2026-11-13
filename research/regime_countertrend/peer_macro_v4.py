"""CFM-V4: historical residual-return peers and ETF macro latent factors.

All grouping/scaling/labels from strictly earlier years. Public OHLC signal-date
research only; no trading, portfolio PnL, or live promotion.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss

from .sector_price_sources_v3 import manifest_load
from .sector_hierarchy_v3 import (
    panel_from_sources,run_hierarchy,_eligible,_fit_supervisor,
    _input_latent,MIN_GLOBAL,MIN_SYMBOL,THRESHOLD,C,
    _balanced_weights
)
from .feature_coverage_v3 import FullCoverageFactorTransformer
from .correlated_factor_model import FEATURES

MACRO_ETFS=("SPY","SMH","IWM","TLT","HYG","GLD")
MACRO_COLS=tuple(
    [f"{s}_ret5" for s in MACRO_ETFS]+[
    "SMH_minus_SPY","IWM_minus_SPY","HYG_minus_TLT","GLD_minus_SPY"
])
MACRO_PC=3
PEER_RAW_THRESHOLD=.55
PEER_RESIDUAL_THRESHOLD=.25
MIN_PAIR_DAYS=126
MAX_PEERS=3
MIN_PEER_EVENTS=40
MIN_PEER_CLASSES=8
PEER_WEIGHT=.30
SYMBOL_WEIGHT=.20

def _daily_ret(asset):
    d=asset[["date","close"]].copy()
    if d.date.duplicated().any():raise ValueError("duplicate stock trading days")
    values=pd.to_numeric(d.close,errors="raise")
    return pd.Series(values.pct_change().to_numpy(),
                     index=d.date.astype(str)).sort_index()

def discover_residual_peers(prices,manifest,year):
    """Fit separate stock betas to QQQ using dates BEFORE Jan 1 of year."""
    cutoff=f"{int(year)}-01-01"
    if "QQQ" not in prices:raise ValueError("missing QQQ for residualization")
    baseline=_daily_ret(prices["QQQ"])
    stock=[
        a for a in manifest["universe"]
        if a["model_eligible"] and a["symbol"] in prices
    ]
    residual={}
    original={}
    for a in stock:
        ticker=a["symbol"]
        joined=pd.concat({"stock":_daily_ret(prices[ticker]),
                          "qqq":baseline},axis=1).loc[lambda x:x.index<cutoff].dropna()
        if len(joined)<MIN_PAIR_DAYS or joined.qqq.var()<=1e-12:
            continue
        beta=float(joined.stock.cov(joined.qqq)/joined.qqq.var())
        residual[ticker]=joined.stock-beta*joined.qqq
        original[ticker]=joined.stock
    report=[]
    for i,a in enumerate(stock):
        x=a["symbol"]
        if x not in residual:continue
        for b in stock[i+1:]:
            y=b["symbol"]
            if y not in residual:continue
            pair=pd.concat({"x":residual[x],"y":residual[y]},axis=1).dropna()
            raw=pd.concat({"x":original[x],"y":original[y]},axis=1).dropna()
            if len(pair)<MIN_PAIR_DAYS or len(raw)<MIN_PAIR_DAYS:
                continue
            residual_corr=float(pair.x.corr(pair.y))
            raw_corr=float(raw.x.corr(raw.y))
            eligible=bool(np.isfinite(residual_corr) and np.isfinite(raw_corr)
                  and residual_corr>=PEER_RESIDUAL_THRESHOLD
                  and raw_corr>=PEER_RAW_THRESHOLD)
            report.append({"year":int(year),"symbol_a":x,"symbol_b":y,
                "industry_a":a["industry"],"industry_b":b["industry"],
                "same_manual_industry":a["industry"]==b["industry"],
                "n_shared":len(pair),"residual_corr":residual_corr,
                "raw_corr":raw_corr,"pair_eligible":eligible,
                "prior_date_end":str(pair.index[-1])})
    pair_table=pd.DataFrame(report)
    peers={}
    for a in stock:
        sym=a["symbol"]
        candidates=[]
        for row in report:
            if not row["pair_eligible"]:continue
            other=(row["symbol_b"] if row["symbol_a"]==sym else
                row["symbol_a"] if row["symbol_b"]==sym else None)
            if other:
                candidates.append((other,row["residual_corr"]))
        candidates.sort(key=lambda x:(-x[1],x[0]))
        peers[sym]=[name for name,_ in candidates[:MAX_PEERS]]
    return peers,pair_table

def macro_history(prices):
    missing=set(MACRO_ETFS)-set(prices)
    if missing:raise ValueError(f"missing required macro ETFs: {sorted(missing)}")
    daily=pd.DataFrame({sym:_daily_ret(prices[sym]) for sym in MACRO_ETFS})
    # Five-session *simple* returns, adjusted for distributions/splits by provider.
    close=pd.DataFrame({sym:pd.Series(
        pd.to_numeric(prices[sym].close).to_numpy(dtype=float),
        index=prices[sym].date.astype(str)) for sym in MACRO_ETFS}).sort_index()
    base=pd.DataFrame(index=close.index)
    for sym in MACRO_ETFS:
        base[f"{sym}_ret5"]=close[sym].pct_change(5,fill_method=None)
    for lhs,rhs in (("SMH","SPY"),("IWM","SPY"),("HYG","TLT"),("GLD","SPY")):
        base[f"{lhs}_minus_{rhs}"]=base[f"{lhs}_ret5"]-base[f"{rhs}_ret5"]
    base.index.name="date"
    return base.reset_index()[["date",*MACRO_COLS]]

class MacroPCA:
    def fit(self,training_daily):
        x=training_daily[list(MACRO_COLS)].astype(float)
        if len(x)<126 or x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
            raise ValueError("not enough valid training macro factor rows")
        self.scale=StandardScaler().fit(x)
        self.pca=PCA(n_components=MACRO_PC).fit(
            np.clip(self.scale.transform(x),-8,8))
        return self
    def transform(self,values):
        x=values[list(MACRO_COLS)].astype(float)
        if x.isna().any().any() or not np.isfinite(x.to_numpy()).all():
            raise ValueError("no forward-fill: some ETF macro features missing")
        return self.pca.transform(
            np.clip(self.scale.transform(x),-8,8))

def _full_model_frame(t,etfs):
    merged=t.merge(etfs,on="date",how="left",validate="many_to_one")
    if len(merged)!=len(t) or merged[list(MACRO_COLS)].isna().any().any():
        raise ValueError("timestamp-specific macro features not aligned")
    return merged

def fit_walkforward_v4(prices,stock_features,events,manifest,first_year=2022):
    if events.empty:raise ValueError("no symbol events")
    macro=macro_history(prices)
    all_data=_full_model_frame(events,macro)
    all_data["win"]=pd.to_numeric(all_data.win).astype(int)
    forecasts=[];fold_stats=[];peer_rows=[]
    for year in sorted(int(y) for y in all_data.year.unique() if y>=first_year):
        cutoff=f"{year}-01-01"
        test=all_data[all_data.year==year].copy()
        train=all_data[(all_data.year<year)&(all_data.exit_date<cutoff)].copy()
        if test.empty:continue
        if not _eligible(train,MIN_GLOBAL,15):
            fold_stats.append({"year":year,"status":"HOLD_INSUFFICIENT_GLOBAL_TRAINING",
                               "n_train":len(train),"n_test":len(test)})
            continue
        hist=stock_features[(stock_features.date_ny<cutoff)].dropna(
            subset=list(FEATURES))
        factors=FullCoverageFactorTransformer().fit(hist)
        etf_history=macro[(macro.date<cutoff)].dropna(subset=list(MACRO_COLS))
        macro_pca=MacroPCA().fit(etf_history)
        peers,peer_edges=discover_residual_peers(prices,manifest,year)
        if not peer_edges.empty:peer_rows.extend(peer_edges.to_dict("records"))
        a=np.column_stack([
            _input_latent(factors,train),macro_pca.transform(train)])
        b=np.column_stack([
            _input_latent(factors,test),macro_pca.transform(test)])
        global_model=_fit_supervisor(train,a)
        global_prob=global_model.predict_proba(b)[:,1]
        peer_p=np.full(len(test),np.nan)
        stock_p=np.full(len(test),np.nan)
        peer_eligible=0
        for sym in test.symbol.unique():
            peer_symbols=peers.get(sym,[])
            source=train[train.symbol.isin(peer_symbols)]
            if len(peer_symbols)<2 or source.symbol.nunique()<2 or not _eligible(
                source,MIN_PEER_EVENTS,MIN_PEER_CLASSES):
                continue
            clf=_fit_supervisor(source,np.column_stack([
                 _input_latent(factors,source),macro_pca.transform(source)]))
            mask=(test.symbol==sym).to_numpy()
            peer_p[mask]=clf.predict_proba(b[mask])[:,1]
            peer_eligible+=1
        symbol_eligible=0
        for sym in test.symbol.unique():
            source=train[train.symbol==sym]
            if not _eligible(source,MIN_SYMBOL,6):continue
            clf=_fit_supervisor(source,np.column_stack([
                 _input_latent(factors,source),macro_pca.transform(source)]))
            mask=(test.symbol==sym).to_numpy()
            stock_p[mask]=clf.predict_proba(b[mask])[:,1]
            symbol_eligible+=1
        peer_available=np.isfinite(peer_p)
        stock_available=np.isfinite(stock_p)
        combined=(
            (1-PEER_WEIGHT*peer_available-SYMBOL_WEIGHT*stock_available)*global_prob+
            PEER_WEIGHT*np.nan_to_num(peer_p,nan=0)+
            SYMBOL_WEIGHT*np.nan_to_num(stock_p,nan=0)
        )
        if not np.isfinite(combined).all():raise ValueError("invalid prediction")
        for i,(_,r) in enumerate(test.iterrows()):
            forecasts.append({"year":year,"date":r.date,"symbol":r.symbol,
                "industry":r.industry,"event":r.event,"win":int(r.win),
                "net_20bp":float(r.net_20bp),
                "macro_market_probability":float(global_prob[i]),
                "peer_probability":float(peer_p[i]) if peer_available[i] else None,
                "symbol_probability":float(stock_p[i]) if stock_available[i] else None,
                "macro_peer_probability":float(combined[i]),
                "macro_market_selected":bool(global_prob[i]>=THRESHOLD),
                "macro_peer_selected":bool(combined[i]>=THRESHOLD),
                "peer_available":bool(peer_available[i]),
                "symbol_available":bool(stock_available[i]),
                "peer_symbols":"|".join(peers.get(r.symbol,[])),
                "peer_cohort_excludes_target":True})
        fold_stats.append({"year":year,"status":"FITTED",
             "n_train":len(train),"n_test":len(test),
             "last_train_exit":str(train.exit_date.max()),
             "peer_models":peer_eligible,"symbol_models":symbol_eligible,
             "eligible_peer_edges":int(peer_edges.pair_eligible.sum()) if len(peer_edges) else 0,
             "macro_pcs":MACRO_PC,"macro_columns":len(MACRO_COLS),
             "macro_explained_variance":float(macro_pca.pca.explained_variance_ratio_.sum()),
             "indicator_columns":len(FEATURES)})
    p=pd.DataFrame(forecasts);stats=pd.DataFrame(fold_stats)
    edges=pd.DataFrame(peer_rows)
    meta={"status":"HOLD_EXPLORATORY_PEER_AND_ETF_MACRO",
      "n_event_predictions":len(p),"years":stats.to_dict("records"),
      "peer_raw_threshold":PEER_RAW_THRESHOLD,
      "peer_market_residual_threshold":PEER_RESIDUAL_THRESHOLD,
      "max_peers":MAX_PEERS,"minimum_pair_days":MIN_PAIR_DAYS,
      "min_peer_train_events":MIN_PEER_EVENTS,
      "macro_columns":list(MACRO_COLS),"macro_pcs":MACRO_PC,
      "weights":{"market":0.50,"peer":PEER_WEIGHT,
         "symbol":SYMBOL_WEIGHT,"if_missing":"weight_returns_to_market"},
      "no_leakage_measures":[
          "Correlation and beta fitted on returns strictly before evaluation year",
          "No target-symbol event labels included in its peer-only model",
          "ETF PCA and indicator grouping fitted on preceding years only",
          "Training label trades must have exited before January 1"
      ],
      "not_independent_test":True,"promotion_allowed":False}
    return p,stats,edges,meta

def compare_with_v3(v4,v3):
    if v4.empty or v3.empty:raise ValueError("missing comparable model predictions")
    old=v3[["date","symbol","year","global_selected","hierarchical_selected",
            "net_20bp"]].rename(columns={
                "net_20bp":"v3_return"})
    z=v4.merge(old,on=["date","symbol","year"],validate="one_to_one",how="left")
    if len(z)!=len(v4) or z.v3_return.isna().any() or (
        (z.net_20bp-z.v3_return).abs()>.000001).any():
        raise ValueError("model cohorts or trade exits are not comparable")
    metrics=[]
    for label,col in [
        ("NO_FILTER",None),
        ("V3_MARKET","global_selected"),
        ("V3_INDUSTRY_AND_SYMBOL","hierarchical_selected"),
        ("V4_MARKET_WITH_ETF_MACRO","macro_market_selected"),
        ("V4_MACRO_RESIDUAL_PEER_AND_SYMBOL","macro_peer_selected")]:
        kept=z if col is None else z[z[col]]
        metrics.append({"model":label,"opportunities":len(z),
           "selected":len(kept),"mean_net_per_opportunity":float(
             kept.net_20bp.sum()/len(z)),
           "mean_net_per_selected":float(kept.net_20bp.mean()) if len(kept) else None,
           "losses_selected":int((kept.net_20bp<0).sum()),
           "worst_selected":float(kept.net_20bp.min()) if len(kept) else None})
    annual=[]
    for (year,industry),g in z.groupby(["year","industry"]):
        for label,col in [
            ("V3_MARKET","global_selected"),
            ("V3_INDUSTRY_AND_SYMBOL","hierarchical_selected"),
            ("V4_MARKET_WITH_ETF_MACRO","macro_market_selected"),
            ("V4_MACRO_RESIDUAL_PEER_AND_SYMBOL","macro_peer_selected")]:
            keep=g[g[col]]
            annual.append({"year":year,"industry":industry,"model":label,
               "n":len(g),"selected":len(keep),
               "mean_net_per_opportunity":float(keep.net_20bp.sum()/len(g))})
    return pd.DataFrame(metrics),pd.DataFrame(annual)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-dir",default="results/regime_countertrend/universe_v3_prices")
    parser.add_argument("--baseline",default="results/regime_countertrend/sector_v3/pooled_industry_symbol_predictions.csv")
    parser.add_argument("--out",default="results/regime_countertrend/peer_macro_v4")
    parser.add_argument("--manifest",default="research/regime_countertrend/universe_sector_v3.json")
    args=parser.parse_args()
    folder=Path(args.out);folder.mkdir(parents=True,exist_ok=True)
    manifest=manifest_load(args.manifest)
    # The manifest-listed crypto symbols and leveraged/inverse ETFs never produce stock labels.
    folder_data=Path(args.source_dir)
    required=["QQQ",*MACRO_ETFS]
    missing=[s for s in required if not (folder_data/f"{s}.csv").exists()]
    if missing:
        raise ValueError("Missing ETF macro benchmark data: "+",".join(missing))
    market={sym:pd.read_csv(folder_data/f"{sym}.csv") for sym in required}
    stocks,feat,events,errors=panel_from_sources(manifest,folder_data)
    if len(stocks)!=14 or errors:
        raise ValueError(f"Stock source HOLD: {errors}")
    all_prices={**market,**stocks}
    predictions,annual,edges,meta=fit_walkforward_v4(all_prices,feat,events,manifest)
    if len(predictions)<100:raise ValueError("Insufficient event predictions")
    comparisons,industry=compare_with_v3(predictions,pd.read_csv(args.baseline))
    predictions.to_csv(folder/"probabilities.csv",index=False)
    annual.to_csv(folder/"fold_training_audit.csv",index=False)
    edges.to_csv(folder/"historical_residual_peer_edges.csv",index=False)
    comparisons.to_csv(folder/"model_comparisons.csv",index=False)
    industry.to_csv(folder/"year_industry_comparison.csv",index=False)
    meta["model_comparisons"]=comparisons.to_dict("records")
    (folder/"decision.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    print("PEER_MACRO_V4_STATUS",json.dumps({
      "status":meta["status"],"evaluated":len(predictions),
      "peer_events":int(predictions.peer_available.sum()),
      "peer_eligible_pairs":int(edges.pair_eligible.sum()) if len(edges) else 0,
      "evaluation_folds":sorted(int(y) for y in predictions.year.unique()),
      "models":meta["model_comparisons"],"promotion_allowed":False
    },ensure_ascii=False))
if __name__=="__main__":main()
