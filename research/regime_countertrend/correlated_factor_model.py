"""Kalman CFM-V2: correlated-column blocks -> 1 PCA factor per block -> ridge logistic.

This is an observational QLD OHLC proxy, not production Kalman signals.
Group discovery, scaling, PCA and logistic fit use *only preceding years*.
Singleton indicators are intentionally discarded, never used as lone features.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

from .failure_diagnostics import run as proxy_signals
from .robust_walkforward import build_events

FEATURES = (
 "qqq_ret5","qqq_ret20","qqq_ret60","qld_ret5","qld_ret20",
 "qqq_ma20_dist","qqq_ma60_dist","qqq_rsi14","rsi_delta3",
 "macd_hist_pct","macd_delta3","bb_pct_b",
 "qqq_atr_pct","qld_atr_pct","qqq_rv20","qld_rv20",
 "adx14","adx_delta3","qld_volume_ratio","qqq_volume_ratio"
)
CORR_THRESHOLD = 0.62
PREDICTION_THRESHOLD = 0.55
REGULARIZATION_C = 0.25
MIN_TRAIN_EVENTS = 24
MIN_CLASSES = 7
FIRST_EVAL_YEAR = 2020

def feature_frame(prices):
    d=prices.sort_values("date_ny").reset_index(drop=True).copy()
    if d.date_ny.duplicated().any():raise ValueError("duplicate price dates")
    for symbol in ("qqq","qld"):
        close=d[f"close_{symbol}"].astype(float)
        for days in (5,20):
            d[f"{symbol}_ret{days}"]=close.pct_change(days)
        d[f"{symbol}_rv20"]=close.pct_change().rolling(20).std()*np.sqrt(252)
        high=d[f"high_{symbol}"].astype(float)
        low=d[f"low_{symbol}"].astype(float)
        tr=pd.concat([high-low,(high-close.shift(1)).abs(),
             (low-close.shift(1)).abs()],axis=1).max(axis=1)
        atr=tr.ewm(alpha=1/14,min_periods=14,adjust=False).mean()
        d[f"{symbol}_atr_pct"]=atr/close
        d[f"{symbol}_volume_ratio"]=d[f"volume_{symbol}"]/d[f"volume_{symbol}"].shift(1).rolling(20).median()
    q=d.close_qqq.astype(float)
    d["qqq_ret60"]=q.pct_change(60)
    d["qqq_ma20_dist"]=q/q.rolling(20).mean()-1
    d["qqq_ma60_dist"]=q/q.rolling(60).mean()-1
    delta=q.diff()
    gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-delta).clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+gain/loss.replace(0,np.nan))
    rsi=rsi.where(~((loss==0)&(gain>0)),100)
    d["qqq_rsi14"]=rsi
    d["rsi_delta3"]=rsi-rsi.shift(3)
    e12=q.ewm(span=12,min_periods=12,adjust=False).mean()
    e26=q.ewm(span=26,min_periods=26,adjust=False).mean()
    macd=e12-e26
    hist=(macd-macd.ewm(span=9,adjust=False,min_periods=9).mean())/q
    d["macd_hist_pct"]=hist
    d["macd_delta3"]=hist-hist.shift(3)
    ma=q.rolling(20).mean();std=q.rolling(20).std()
    d["bb_pct_b"]=(q-ma+2*std)/(4*std.replace(0,np.nan))
    hi=d.high_qqq.astype(float);lo=d.low_qqq.astype(float)
    up=hi.diff();down=-lo.diff()
    plus=up.where((up>down)&(up>0),0)
    minus=down.where((down>up)&(down>0),0)
    tr=pd.concat([hi-lo,(hi-q.shift(1)).abs(),(lo-q.shift(1)).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    plusdi=100*plus.ewm(alpha=1/14,min_periods=14,adjust=False).mean()/atr
    minusdi=100*minus.ewm(alpha=1/14,min_periods=14,adjust=False).mean()/atr
    dx=100*(plusdi-minusdi).abs()/(plusdi+minusdi).replace(0,np.nan)
    d["adx14"]=dx.ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    d["adx_delta3"]=d.adx14-d.adx14.shift(3)
    return d[["date_ny",*FEATURES]]

def correlation_groups(daily,threshold=CORR_THRESHOLD):
    if not 0<threshold<1:raise ValueError("invalid correlation threshold")
    if len(daily)<100:raise ValueError("insufficient daily observations")
    corr=daily[list(FEATURES)].corr().abs().fillna(0)
    distance=(1-corr).clip(0,1).to_numpy(copy=True)
    np.fill_diagonal(distance,0)
    hier=linkage(squareform(distance,checks=False),method="average")
    assignment=fcluster(hier,t=1-threshold,criterion="distance")
    groups=[[name for name,k in zip(FEATURES,assignment) if k==cluster]
            for cluster in sorted(set(assignment))]
    non_single=[g for g in groups if len(g)>=2]
    non_single.sort(key=lambda g:(-len(g),FEATURES.index(g[0])))
    single=[g[0] for g in groups if len(g)==1]
    if len(non_single)<2:raise ValueError("too few correlated feature blocks")
    return non_single,single

class CorrelatedFactors:
    def fit(self,daily):
        self.groups,self.excluded=correlation_groups(daily)
        self.scalers=[];self.pcas=[]
        for group in self.groups:
            scale=StandardScaler().fit(daily[group])
            matrix=np.clip(scale.transform(daily[group]),-8,8)
            pca=PCA(n_components=1,svd_solver="full").fit(matrix)
            self.scalers.append(scale);self.pcas.append(pca)
        return self
    def transform(self,rows):
        factors=[]
        for group,scale,pca in zip(self.groups,self.scalers,self.pcas):
            x=np.clip(scale.transform(rows[group]),-8,8)
            factors.append(pca.transform(x).ravel()/np.sqrt(pca.explained_variance_[0]))
        return np.column_stack(factors)
    def metadata(self,year):
        return [{
            "trained_before_year":year,"block":f"GROUP_{i+1}",
            "columns":group,"column_count":len(group),
            "pc1_explained_variance":float(pc.explained_variance_ratio_[0]),
        } for i,(group,pc) in enumerate(zip(self.groups,self.pcas))]

def add_event_context(values,events):
    return np.column_stack([values,(events.event=="DOWN_RALLY").astype(int).to_numpy()])

def apply_models(prices,events,first_year=FIRST_EVAL_YEAR):
    daily=feature_frame(prices)
    joined=events.merge(daily,left_on="date",right_on="date_ny",
                        how="left",validate="one_to_one")
    if joined[list(FEATURES)].isna().any().any() or not np.isfinite(
        joined[list(FEATURES)].to_numpy()).all():
        raise ValueError("missing or nonfinite signal-time features")
    if joined.date.duplicated().any():raise ValueError("duplicated signals")
    joined["win"]=(joined.net_20bp>0).astype(int)
    fold_rows=[];prediction_rows=[];metadata=[]
    for year in sorted(int(y) for y in joined.year.unique() if int(y)>=first_year):
        test=joined[joined.year==year].copy()
        train=joined[(joined.year<year)&
             (pd.to_datetime(joined.exit_date)<pd.Timestamp(f"{year}-01-01"))].copy()
        fold={"year":year,"train_events":len(train),"test_events":len(test),
              "train_last_exit":str(train.exit_date.max()) if len(train) else None}
        if len(train)<MIN_TRAIN_EVENTS or train.year.nunique()<3 or (
            min(int(train.win.sum()),int((1-train.win).sum()))<MIN_CLASSES):
            fold["status"]="HOLD_INSUFFICIENT_TRAINING"
            fold_rows.append(fold);continue
        causal_daily=daily[(daily.date_ny<f"{year}-01-01")].dropna().copy()
        if len(causal_daily)<100:raise ValueError("missing preceding daily history")
        blocks=CorrelatedFactors().fit(causal_daily)
        x_train=add_event_context(blocks.transform(train),train)
        x_test=add_event_context(blocks.transform(test),test)
        group_model=LogisticRegression(C=REGULARIZATION_C,max_iter=1500).fit(x_train,train.win)
        group_prob=group_model.predict_proba(x_test)[:,1]
        # Comparison only: each original column used individually with same C.
        raw_scale=StandardScaler().fit(train[list(FEATURES)])
        raw_train=add_event_context(np.clip(raw_scale.transform(train[list(FEATURES)]),-8,8),train)
        raw_test=add_event_context(np.clip(raw_scale.transform(test[list(FEATURES)]),-8,8),test)
        raw_model=LogisticRegression(C=REGULARIZATION_C,max_iter=1500).fit(raw_train,train.win)
        raw_prob=raw_model.predict_proba(raw_test)[:,1]
        group_take=(group_prob>=PREDICTION_THRESHOLD)
        raw_take=(raw_prob>=PREDICTION_THRESHOLD)
        for model_name,mask,prob in (
            ("BASELINE",np.ones(len(test),dtype=bool),np.full(len(test),float(train.win.mean()))),
            ("GROUPED_PCA_RIDGE",group_take,group_prob),
            ("RAW_COLUMN_RIDGE",raw_take,raw_prob)):
            part=test.loc[mask]
            fold_rows.append({**fold,"status":"FITTED","model":model_name,
                "factor_groups":len(blocks.groups),
                "grouped_columns":sum(len(g) for g in blocks.groups),
                "orphans_dropped":len(blocks.excluded),
                "selected_n":int(mask.sum()),"opportunities":len(test),
                "selected_net_sum":float(part.net_20bp.sum()),
                "net_per_opportunity":float(part.net_20bp.sum()/len(test)),
                "mean_net_taken":float(part.net_20bp.mean()) if len(part) else None,
                "negative_taken":int((part.net_20bp<0).sum()),
                "worst_taken":float(part.net_20bp.min()) if len(part) else None,
                "prob_brier":float(brier_score_loss(test.win,prob)),
                "probability_threshold":PREDICTION_THRESHOLD})
        for i,(_,r) in enumerate(test.iterrows()):
            prediction_rows.append({"date":r.date,"year":year,"event":r.event,
               "exit_date":r.exit_date,"actual_win":int(r.win),
               "net_20bp":float(r.net_20bp),"group_prob":float(group_prob[i]),
               "raw_prob":float(raw_prob[i]),"group_selected":bool(group_take[i]),
               "raw_selected":bool(raw_take[i]),"train_n":len(train),
               "num_factors":len(blocks.groups)})
        metadata.extend(blocks.metadata(year))
    folds=pd.DataFrame(fold_rows)
    predictions=pd.DataFrame(prediction_rows)
    factor_rows=pd.DataFrame([{**m,"columns":"|".join(m["columns"])} for m in metadata])
    eligible=folds[folds.status=="FITTED"]
    summaries=[]
    for name,g in eligible.groupby("model"):
        n=int(g.opportunities.sum())
        summaries.append({"model":name,"evaluated_opportunities":n,
            "trades_taken":int(g.selected_n.sum()),
            "sum_returns_not_portfolio":float(g.selected_net_sum.sum()),
            "mean_net_per_opportunity":float(g.selected_net_sum.sum()/n),
            "mean_brier_across_folds":float(g.prob_brier.mean())})
    meta={"status":"HOLD_EXPLORATORY_GROUPED_MODEL",
          "feature_engineering":"training-only absolute Pearson agglomeration + PCA(1) each non-singleton block",
          "corr_threshold":CORR_THRESHOLD,
          "raw_column_count":len(FEATURES),
          "probability_threshold":PREDICTION_THRESHOLD,"ridge_C":REGULARIZATION_C,
          "first_year":first_year,"eligible_eval_events":len(predictions),
          "evaluated_folds":sorted(int(y) for y in predictions.year.unique()) if len(predictions) else [],
          "models":summaries,
          "promotion_allowed":False,
          "limitations":["Research-only QLD daily OHLC proxy; not LIVE Kalman signals or broker fills",
             "Training labels use next open, +3/-3, 4-day and 20bp synthetic fills",
             "Groups, standardizers, PCA and supervised model fitted anew on previous years only",
             "2025-2026 is already examined, not an untouched independent test",
             "Tiny event sample and multiple prior hypothesis searches; alpha not confirmed",
             "No new eligible signals after 2026-09-04; do not invent fresh OOS returns",
             "No dynamic portfolio MDD, position overlap, liquidity or verified slippage"]}
    return folds,predictions,factor_rows,meta

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--prices",default="research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
    a.add_argument("--out",default="results/regime_countertrend/cfm_v2")
    v=a.parse_args()
    prices=pd.read_csv(v.prices)
    events,_=proxy_signals(prices)
    gap_events=build_events(prices,events[["date","event"]])
    folds,pred,blocks,meta=apply_models(prices,gap_events)
    out=Path(v.out);out.mkdir(parents=True,exist_ok=True)
    folds.to_csv(out/"annual_grouped_model_comparison.csv",index=False)
    pred.to_csv(out/"signal_probabilities.csv",index=False)
    blocks.to_csv(out/"feature_groups_by_training_fold.csv",index=False)
    (out/"decision.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    print("CFM_V2_MODEL",json.dumps(meta,ensure_ascii=False))
    print("CFM_V2_GROUPS",blocks[blocks.trained_before_year==2025].to_json(orient="records"))
    print("CFM_V2_ANNUAL",folds[folds.status=="FITTED"].to_json(orient="records"))
if __name__=="__main__":main()
