"""CFM-V3 full feature-accountability audit: no silent drop of singletons.

High-correlated features -> one unsupervised PC per discovered block.
Low-correlated remaining features -> one *joint residual group*, retain ALL PCs
so their information is represented, rather than discarding them or treating
them as independent trading filters. Fit group discovery and PCA on past ONLY.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from .correlated_factor_model import (
    FEATURES,CORR_THRESHOLD,PREDICTION_THRESHOLD,REGULARIZATION_C,
    correlation_groups,feature_frame,add_event_context
)
from .failure_diagnostics import run as proxy_signals
from .robust_walkforward import build_events

class FullCoverageFactorTransformer:
    def fit(self,history):
        if history[list(FEATURES)].isna().any().any():
            raise ValueError("training features contain missing values")
        x=history[list(FEATURES)].astype(float)
        if not np.isfinite(x.to_numpy()).all():
            raise ValueError("nonfinite training inputs")
        blocks,singletons=correlation_groups(x)
        self.high_corr_blocks=[list(b) for b in blocks]
        self.residual_block=list(singletons)
        self.blocks=blocks+([singletons] if singletons else [])
        self.scalers=[]
        self.pcas=[]
        self.factor_names=[]
        self.lineage=[]
        seen=set()
        for k,columns in enumerate(self.blocks):
            if seen.intersection(columns):raise ValueError("overlapping columns")
            seen.update(columns)
            scale=StandardScaler().fit(x[columns])
            z=np.clip(scale.transform(x[columns]),-8,8)
            is_residual=bool(singletons) and k==len(blocks)
            npc=len(columns) if is_residual else 1
            pca=PCA(n_components=npc,svd_solver="full").fit(z)
            self.scalers.append(scale);self.pcas.append(pca)
            group_name=("RESIDUAL_CONTEXT" if is_residual else f"CORRELATED_{k+1}")
            for pc in range(npc):
                fname=f"{group_name}_PC{pc+1}"
                self.factor_names.append(fname)
                for col,coef in zip(columns,pca.components_[pc]):
                    self.lineage.append({
                        "factor":fname,"group":group_name,"feature":col,
                        "loading":float(coef),
                        "variance_explained":float(pca.explained_variance_ratio_[pc]),
                        "group_size":len(columns),
                        "group_is_correlated":not is_residual})
        if set(FEATURES)!=seen or len(seen)!=len(FEATURES):
            raise ValueError("feature mapping not complete")
        if not all(np.isfinite(v["loading"]) for v in self.lineage):
            raise ValueError("nonfinite factor loading")
        self.used_features=tuple(sorted(seen))
        return self

    def transform(self,rows):
        if not self.blocks:raise ValueError("transformer not fitted")
        if not set(FEATURES).issubset(rows):raise ValueError("missing feature inputs")
        x=rows[list(FEATURES)].astype(float).to_numpy()
        if not np.isfinite(x).all():raise ValueError("nonfinite scoring inputs")
        out=[]
        for cols,scale,pca in zip(self.blocks,self.scalers,self.pcas):
            z=np.clip(scale.transform(rows[cols]),-8,8)
            PCs=pca.transform(z)
            PCs/=np.sqrt(np.maximum(pca.explained_variance_,1e-12))
            out.append(PCs)
        result=np.column_stack(out)
        if result.shape[1]!=len(self.factor_names) or not np.isfinite(result).all():
            raise ValueError("invalid latent factors")
        return result

def group_feature_audit(prices):
    daily=feature_frame(prices)
    train=daily[daily.date_ny<"2025-01-01"].dropna()
    transformer=FullCoverageFactorTransformer().fit(train)
    return transformer,{
        "raw_feature_count":len(FEATURES),"computed_feature_count":len(FEATURES),
        "model_input_coverage":len(transformer.used_features),
        "omitted_features":sorted(set(FEATURES)-set(transformer.used_features)),
        "correlated_groups":transformer.high_corr_blocks,
        "residual_low_correlation_group":transformer.residual_block,
        "latent_factor_count":len(transformer.factor_names),
        "nonzero_factor_loadings":sum(abs(x["loading"])>1e-12 for x in transformer.lineage),
        "coverage_status":"ALL_20_FEATURES_MAPPED_TO_LATENT_BLOCKS",
        "warning":"Residual 3-column group retains 3 principal components; no correlation threshold is claimed for that group.",
        "promote_to_live":False
    }

def audit_walkforward(prices,events):
    daily=feature_frame(prices)
    merged=events.merge(daily,left_on="date",right_on="date_ny",
                        validate="one_to_one")
    if len(merged)!=len(events):raise ValueError("unmatched event date")
    merged["label"]=(merged.net_20bp>0).astype(int)
    if merged[list(FEATURES)].isna().any().any():
        raise ValueError("unavailable features for events")
    rows=[];groups=[]
    for year in (2022,2023,2024,2025,2026):
        test=merged[merged.year==year]
        train=merged[(merged.year<year)&(merged.exit_date<f"{year}-01-01")]
        if len(test)==0:continue
        if len(train)<24 or min(int(train.label.sum()),int((1-train.label).sum()))<7:
            rows.append({"year":year,"status":"HOLD_TRAIN_SAMPLE"});continue
        context=daily[(daily.date_ny<f"{year}-01-01")].dropna()
        model=FullCoverageFactorTransformer().fit(context)
        logits=LogisticRegression(C=REGULARIZATION_C,max_iter=1500)
        logits.fit(add_event_context(model.transform(train),train),train.label)
        p=logits.predict_proba(add_event_context(model.transform(test),test))[:,1]
        keep=p>=PREDICTION_THRESHOLD
        rows.append({"year":year,"status":"FITTED","opportunities":len(test),
           "selected":int(keep.sum()),
           "net_sum":float(test.loc[keep,"net_20bp"].sum()),
           "mean_per_opportunity":float(test.loc[keep,"net_20bp"].sum()/len(test)),
           "brier":float(brier_score_loss(test.label,p)),
           "n_features_used":len(model.used_features),
           "n_factors":len(model.factor_names),
           "last_train_exit":str(train.exit_date.max()),
           "trained_before":f"{year}-01-01",
           "approval_allowed":False})
        for b in model.lineage:
            groups.append({"year":year,**b})
    return pd.DataFrame(rows),pd.DataFrame(groups)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--prices",default="research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
    p.add_argument("--out",default="results/regime_countertrend/cfm_v3_coverage")
    v=p.parse_args()
    prices=pd.read_csv(v.prices)
    transformer,manifest=group_feature_audit(prices)
    signals,_=proxy_signals(prices)
    events=build_events(prices,signals[["date","event"]])
    folds,lineage=audit_walkforward(prices,events)
    out=Path(v.out);out.mkdir(parents=True,exist_ok=True)
    folds.to_csv(out/"full_coverage_walkforward.csv",index=False)
    lineage.to_csv(out/"training_only_factor_lineage.csv",index=False)
    manifest["fold_results"]=folds.to_dict(orient="records")
    manifest["walkforward_status"]="REVISITED_NOT_INDEPENDENT"
    (out/"feature_coverage.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print("CFM_V3_FEATURE_COVERAGE",json.dumps(manifest,ensure_ascii=False))
if __name__=="__main__":main()
