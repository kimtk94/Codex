"""CFM-V5: price location + candle structure + volume + compression by market regime,
trained and judged in KRW with historical USD/KRW.

Full source history, as-of FX and model folds are isolated by evaluation year.
Signals and intraday execution are synthetic daily OHLC, not broker fills.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

from .feature_coverage_v3 import FullCoverageFactorTransformer
from .correlated_factor_model import FEATURES
from .peer_macro_v4 import macro_history,MacroPCA,MACRO_COLS,_input_latent
from .sector_hierarchy_v3 import panel_from_sources,_fit_supervisor,_eligible,MIN_GLOBAL
from .sector_price_sources_v3 import manifest_load
from .krw_fx_v5 import (
    previous_fx_marks,build_entry_dates,attach_fx,
    summarize,FX_STALE_DAYS
)

DETAIL_GROUPS={
 "PRICE_LOCATION":("range_position_5d","range_position_20d",
                   "distance_high_20d","distance_low_20d"),
 "CANDLE_SHAPE":("close_candle_position","candle_body_pct",
                 "upper_wick_share","lower_wick_share"),
 "VOLUME_BEHAVIOR":("volume_ratio_20d","volume_5to20d",
                    "down_volume_share_5d","dollar_volume_5to20d"),
 "RANGE_COMPRESSION":("true_range_pct","range5_pct",
                      "range20_pct","range_expansion_ratio")
}
DETAIL_COLUMNS=tuple(x for group in DETAIL_GROUPS.values() for x in group)
FX_FEATURES=("usdkrw_ret5","usdkrw_ret20","usdkrw_rv20","usdkrw_ma20_dist")
DETAIL_PC_PER_GROUP=2
FX_PCS=2
CLASSIFIER_C=.10
THRESHOLD=.55
MIN_CLASSES=15
FIRST_TEST_YEAR=2022

def _ratio(a,b):
    return a/b.replace(0,np.nan)

def detail_daily(prices,symbol):
    d=prices.sort_values("date").copy().reset_index(drop=True)
    if d.date.duplicated().any():raise ValueError("duplicate stock days")
    o=d.open.astype(float);h=d.high.astype(float)
    l=d.low.astype(float);c=d.close.astype(float)
    v=d.volume.astype(float)
    if ((h<d[["open","low","close"]].max(axis=1))|
        (l>d[["open","high","close"]].min(axis=1))).any():
        raise ValueError("invalid stock OHLC")
    high5=h.rolling(5,min_periods=5).max()
    low5=l.rolling(5,min_periods=5).min()
    high20=h.rolling(20,min_periods=20).max()
    low20=l.rolling(20,min_periods=20).min()
    ranges=(h-l)
    tr=pd.concat([ranges,(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
    up=np.maximum(o,c);down=np.minimum(o,c)
    down_volume=v.where(c<c.shift(1),0.)
    dollar=v*c
    result=pd.DataFrame({
        "date":d.date.astype(str),"symbol":symbol,
        "range_position_5d":_ratio(c-low5,high5-low5),
        "range_position_20d":_ratio(c-low20,high20-low20),
        "distance_high_20d":_ratio(c,high20)-1,
        "distance_low_20d":_ratio(c,low20)-1,
        "close_candle_position":_ratio(c-l,ranges),
        "candle_body_pct":_ratio(c-o,o),
        "upper_wick_share":_ratio(h-up,ranges),
        "lower_wick_share":_ratio(down-l,ranges),
        "volume_ratio_20d":_ratio(v,v.rolling(20,min_periods=20).mean())-1,
        "volume_5to20d":_ratio(v.rolling(5,min_periods=5).mean(),
                               v.rolling(20,min_periods=20).mean())-1,
        "down_volume_share_5d":_ratio(down_volume.rolling(5,min_periods=5).sum(),
                                     v.rolling(5,min_periods=5).sum()),
        "dollar_volume_5to20d":_ratio(
            dollar.rolling(5,min_periods=5).mean(),
            dollar.rolling(20,min_periods=20).mean())-1,
        "true_range_pct":_ratio(tr,c),
        "range5_pct":_ratio(high5-low5,c),
        "range20_pct":_ratio(high20-low20,c),
        "range_expansion_ratio":_ratio(
            tr.rolling(5,min_periods=5).mean(),
            tr.rolling(20,min_periods=20).mean())-1})
    return result

class GroupedDetails:
    def fit(self,history):
        self.blocks={}
        self.lineage=[]
        used=[]
        for name,cols in DETAIL_GROUPS.items():
            train=history[list(cols)]
            if len(train)<126 or train.isna().any().any():
                raise ValueError(f"{name}: invalid training rows")
            scale=StandardScaler().fit(train)
            pca=PCA(n_components=DETAIL_PC_PER_GROUP,svd_solver="full").fit(
                np.clip(scale.transform(train),-8,8))
            self.blocks[name]=(cols,scale,pca)
            used.extend(cols)
            for pc in range(DETAIL_PC_PER_GROUP):
                for col,loading in zip(cols,pca.components_[pc]):
                    self.lineage.append({"group":name,"component":pc+1,
                        "feature":col,"loading":float(loading),
                        "explained_variance":float(pca.explained_variance_ratio_[pc])})
        if len(used)!=len(set(used)) or set(used)!=set(DETAIL_COLUMNS):
            raise ValueError("detail group feature lineage incomplete")
        return self
    def transform(self,rows):
        arr=[]
        for _,(cols,scale,pca) in self.blocks.items():
            x=rows[list(cols)].astype(float)
            if not np.isfinite(x.to_numpy()).all():
                raise ValueError("scoring detail missing or infinite")
            transformed=pca.transform(np.clip(scale.transform(x),-8,8))
            arr.append(transformed/np.sqrt(np.maximum(
                pca.explained_variance_,1e-12)))
        return np.column_stack(arr)

def fx_daily_features(fx):
    d=fx.sort_values("date").copy().reset_index(drop=True)
    x=d.usdkrw_close.astype(float)
    change=x.pct_change(fill_method=None)
    return pd.DataFrame({
        "date":d.date.astype(str),
        "usdkrw_ret5":x.pct_change(5,fill_method=None),
        "usdkrw_ret20":x.pct_change(20,fill_method=None),
        "usdkrw_rv20":change.rolling(20,min_periods=20).std()*np.sqrt(252),
        "usdkrw_ma20_dist":x/x.rolling(20,min_periods=20).mean()-1})

def fx_asof_signal(signal_days,fx):
    # Use features from the last strictly earlier-dated FX session.
    available=fx_daily_features(fx).sort_values("date").dropna()
    signals=pd.DataFrame({"signal_date":pd.Series(signal_days).astype(str)})
    targets=pd.to_datetime(signals.signal_date).to_numpy(dtype="datetime64[ns]")
    prev=pd.to_datetime(available.date).to_numpy(dtype="datetime64[ns]")
    ix=np.searchsorted(prev,targets,side="left")-1
    if (ix<0).any():raise ValueError("insufficient FX history")
    result=available.iloc[ix].reset_index(drop=True)
    lag=((targets-prev[ix])/np.timedelta64(1,"D"))
    if (lag>FX_STALE_DAYS).any() or (lag<=0).any():
        raise ValueError("FX signal feature stale/future")
    return result[list(FX_FEATURES)].reset_index(drop=True)

def prepare_price_fx_events(assets,source,fx):
    all_events=pd.read_csv(source)
    stock_prices={k:v for k,v in assets.items()
                  if k not in ("QQQ","SPY","SMH","IWM","TLT","HYG","GLD")}
    positioned=build_entry_dates(all_events,stock_prices)
    value=attach_fx(positioned,fx)
    return value

def _market_and_fx_features(regime_events,tech,macro,fx_pca,fx_signal,vol_threshold):
    main=_input_latent(tech,regime_events)
    macro_f=macro.transform(regime_events)
    fx_f=fx_pca.transform(fx_signal)
    highvol=(regime_events.qqq_atr_pct.astype(float).to_numpy()>vol_threshold).astype(float)
    # _input_latent includes 2 category indicators (DOWN_RALLY, SIDE_DIP).
    return np.column_stack([main,macro_f,fx_f,highvol])

def _with_detail(base,detail,events):
    return np.column_stack([base,detail])

def _with_interactions(base,detail,events):
    down=(events.event=="DOWN_RALLY").astype(float).to_numpy()
    side=(events.event=="SIDE_DIP").astype(float).to_numpy()
    high=base[:,-1]
    return np.column_stack([base,detail,detail*down[:,None],
                            detail*side[:,None],detail*high[:,None]])

def annual_krw_detail_models(prices,features,events,fx,macro,details,eval_identity):
    e=events.merge(features.rename(columns={"date_ny":"date"}),
                   on=["date","symbol"],how="left",validate="one_to_one",
                   suffixes=("","_technical"))
    # technical columns were already present in event proxies; only merge if
    # needed. Disallow duplication ambiguity in model matrices.
    for col in FEATURES:
        if col not in e and f"{col}_technical" in e:
            e[col]=e[f"{col}_technical"]
    e=e.merge(details,on=["date","symbol"],how="left",validate="one_to_one")
    e=e.merge(macro,on="date",how="left",validate="many_to_one")
    if e[list(FEATURES)+list(DETAIL_COLUMNS)+list(MACRO_COLS)].isna().any().any():
        raise ValueError("nonfinite/missing technical-detail-macro event columns")
    fx_signals=fx_asof_signal(e.date,fx)
    for field in FX_FEATURES:e[field]=fx_signals[field].to_numpy()
    e["krw_target"]=(e.krw_mark_return>0).astype(int)
    predictions=[];stats=[];lineage=[]
    for year in sorted(int(y) for y in e.year.unique() if int(y)>=FIRST_TEST_YEAR):
        cutoff=f"{year}-01-01"
        train=e[(e.year<year)&(e.exit_date<cutoff)].copy()
        test=e[e.year==year].copy()
        if test.empty:continue
        if not _eligible(train,MIN_GLOBAL,MIN_CLASSES):
            stats.append({"year":year,"status":"HOLD_KRW_TRAINING_INSUFFICIENT",
                          "n_train":len(train),"n_test":len(test)})
            continue
        hist=features[(features.date_ny<cutoff)].dropna(subset=list(FEATURES))
        detail_hist=details[details.date<cutoff].dropna(subset=list(DETAIL_COLUMNS))
        macro_hist=macro[macro.date<cutoff].dropna(subset=list(MACRO_COLS))
        fx_hist=fx_daily_features(fx)
        fx_hist=fx_hist[fx_hist.date<cutoff].dropna(subset=list(FX_FEATURES))
        tech=FullCoverageFactorTransformer().fit(hist)
        micro=GroupedDetails().fit(detail_hist)
        macro_model=MacroPCA().fit(macro_hist)
        fxscale=StandardScaler().fit(fx_hist[list(FX_FEATURES)])
        fxpca=PCA(n_components=2).fit(
            np.clip(fxscale.transform(fx_hist[list(FX_FEATURES)]),-8,8))
        class FXLatent:
            def transform(self,values):
                return fxpca.transform(np.clip(
                    fxscale.transform(values[list(FX_FEATURES)]),-8,8))
        fxmodel=FXLatent()
        vol_threshold=float(hist.qqq_atr_pct.quantile(.75))
        A=_market_and_fx_features(train,tech,macro_model,fxmodel,train,vol_threshold)
        B=_market_and_fx_features(test,tech,macro_model,fxmodel,test,vol_threshold)
        DA=micro.transform(train);DB=micro.transform(test)
        variants={
          "FX_REGIME_BASE":(A,B),
          "FX_REGIME_PLUS_LOCATION_VOLUME":(_with_detail(A,DA,train),
                                             _with_detail(B,DB,test)),
          "FX_REGIME_DETAIL_INTERACTIONS":(_with_interactions(A,DA,train),
                                            _with_interactions(B,DB,test))
        }
        for variant,(x_train,x_test) in variants.items():
            model=LogisticRegression(C=CLASSIFIER_C,max_iter=1800)
            model.fit(x_train,train.krw_target,
                      sample_weight=np.ones(len(train)))
            prob=model.predict_proba(x_test)[:,1]
            selected=prob>=THRESHOLD
            for i,(_,row) in enumerate(test.iterrows()):
                predictions.append({"date":row.date,"year":year,"symbol":row.symbol,
                  "industry":row.industry,"event":row.event,"model":variant,
                  "probability":float(prob[i]),"selected":bool(selected[i]),
                  "net_20bp":float(row.net_20bp),
                  "krw_mark_return":float(row.krw_mark_return),
                  "krw_roundtrip_fx_10bps_each_side":float(
                      row.krw_roundtrip_fx_10bps_each_side),
                  "krw_roundtrip_fx_25bps_each_side":float(
                      row.krw_roundtrip_fx_25bps_each_side),
                  "usd_win":bool(row.usd_net_return>0),
                  "krw_win":bool(row.krw_mark_return>0),
                  "market_high_vol":bool(row.qqq_atr_pct>vol_threshold),
                  "fx_entry_reference":row.entry_fx_reference_date,
                  "fx_exit_reference":row.exit_fx_reference_date})
            chosen=test.iloc[np.flatnonzero(selected)]
            stats.append({"year":year,"status":"FITTED","model":variant,
              "n_train":len(train),"n_test":len(test),"selected":int(selected.sum()),
              "usd_win_rate":float((chosen.usd_net_return>0).mean()) if len(chosen) else None,
              "krw_win_rate":float((chosen.krw_mark_return>0).mean()) if len(chosen) else None,
              "usd_per_opportunity":float(chosen.usd_net_return.sum()/len(test)),
              "krw_per_opportunity":float(chosen.krw_mark_return.sum()/len(test)),
              "krw_10bp_spread_per_opportunity":float(
                  chosen.krw_roundtrip_fx_10bps_each_side.sum()/len(test)),
              "brier_krw_label":float(brier_score_loss(test.krw_target,prob)),
              "latest_train_exit":str(train.exit_date.max()),
              "detail_original_columns":len(DETAIL_COLUMNS),
              "detail_latent_factors":len(DETAIL_GROUPS)*DETAIL_PC_PER_GROUP,
              "fx_original_columns":len(FX_FEATURES),
              "fx_latent_factors":FX_PCS,
              "promotion_allowed":False})
        for item in micro.lineage:lineage.append({"trained_before":cutoff,**item})
    forecast=pd.DataFrame(predictions)
    folds=pd.DataFrame(stats)
    report={"status":"HOLD_KRW_DETAIL_MODEL_UNPROVEN",
      "evaluated_opportunities":int(forecast[forecast.model=="FX_REGIME_BASE"].shape[0])
          if not forecast.empty else 0,
      "detail_features":list(DETAIL_COLUMNS),
      "detail_groups":{k:list(v) for k,v in DETAIL_GROUPS.items()},
      "detail_latents":len(DETAIL_GROUPS)*DETAIL_PC_PER_GROUP,
      "fx_input_columns":list(FX_FEATURES),
      "fx_latents":FX_PCS,
      "market_indicator_columns":len(FEATURES),
      "models":folds[folds.status=="FITTED"].groupby("model").agg(
           opportunities=("n_test","sum"),
           selected=("selected","sum"),
           usd_sum_equivalent=("usd_per_opportunity","mean"),
           krw_sum_equivalent=("krw_per_opportunity","mean"),
           mean_brier=("brier_krw_label","mean")).reset_index().to_dict("records"),
      "prediction_threshold":THRESHOLD,
      "regularization_C":CLASSIFIER_C,
      "FX_quote":"KRW per USD, previous dated daily close",
      "no_future_training":"all groups/labels past closed years only",
      "is_forex_trading_cost_verified":False,
      "live_promotion_allowed":False,
      "limitations":[
        "This year window is repeatedly explored; no untouched holdout",
        "Model includes KRW target win labels, but broker FX fills are unavailable",
        "Actual FX conversion may not occur on each stock trade",
        "Signal-date daily OHLC not intraday real fill and 15m feed remains HOLD",
        "Opportunity-based means are not account equity, MDD, CAGR or tax-return PnL"]}
    return forecast,folds,pd.DataFrame(lineage),report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",default="results/regime_countertrend/universe_v3_prices")
    p.add_argument("--events",default="results/regime_countertrend/sector_v3/all_symbol_proxy_events.csv")
    p.add_argument("--fx",default="results/regime_countertrend/krw_fx_v5/usdkrw_public_daily.csv")
    p.add_argument("--manifest",default="research/regime_countertrend/universe_sector_v3.json")
    p.add_argument("--out",default="results/regime_countertrend/krw_detail_v5")
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    manifest=manifest_load(a.manifest)
    stock_prices,features,events,errors=panel_from_sources(manifest,a.source_dir)
    if errors or len(stock_prices)!=14:
        raise ValueError(f"Missing full 14-stock sample {errors}")
    all_events=pd.read_csv(a.events)
    if len(events)!=len(all_events):
        raise ValueError("V5 and V3 event cohorts differ")
    fx=pd.read_csv(a.fx)
    positioned=build_entry_dates(events,stock_prices)
    valued=attach_fx(positioned,fx)
    details=pd.concat([detail_daily(prices,sym)
                       for sym,prices in stock_prices.items()],ignore_index=True)
    if len(details)!=sum(len(x) for x in stock_prices.values()):
        raise ValueError("detail feature row count mismatch")
    prices={sym:pd.read_csv(Path(a.source_dir)/f"{sym}.csv")
            for sym in ("SPY","SMH","IWM","TLT","HYG","GLD")}
    macro=macro_history(prices)
    predictions,folds,lineage,meta=annual_krw_detail_models(
        stock_prices,features,valued,fx,macro,details,None)
    predictions.to_csv(out/"yearly_krw_detail_predictions.csv",index=False)
    folds.to_csv(out/"annual_krw_models.csv",index=False)
    lineage.to_csv(out/"detail_pca_feature_lineage.csv",index=False)
    (out/"decision.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    summary=[]
    for model,g in predictions.groupby("model"):
        taken=g[g.selected]
        for key in ("net_20bp","krw_mark_return",
                    "krw_roundtrip_fx_10bps_each_side",
                    "krw_roundtrip_fx_25bps_each_side"):
            summary.append({"model":model,"currency":key,
                "opportunities":len(g),"selected":len(taken),
                "win_rate":float((taken[key]>0).mean()) if len(taken) else None,
                "mean_selected":float(taken[key].mean()) if len(taken) else None,
                "mean_opportunity":float(taken[key].sum()/len(g))})
    pd.DataFrame(summary).to_csv(out/"usd_krw_win_rate_ablation.csv",index=False)
    print("KRW_DETAIL_V5",json.dumps({"status":meta["status"],"events":meta["evaluated_opportunities"],
         "models":summary,"promotion_allowed":False},ensure_ascii=False))
if __name__=="__main__":main()
