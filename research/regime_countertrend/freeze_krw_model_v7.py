"""CFM-V7 prospective freeze: build and verify a PORTABLE JSON KRW model.

Train on synthetic US stock price events fully exited by 2026-11-10.
This run is an explicit new retrospectively adjusted data vintage. No rows
on/after 2026-11-11 are permitted in fitting. The model is frozen on
2026-11-15; prospective observation begins 2026-11-16 (XNYS).
The JSON scorer uses NumPy only, never unpickles files. Intended for SHADOW.
"""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .feature_coverage_v3 import FullCoverageFactorTransformer
from .correlated_factor_model import FEATURES
from .peer_macro_v4 import macro_history,MacroPCA,MACRO_COLS,MACRO_ETFS,_input_latent
from .sector_hierarchy_v3 import panel_from_sources
from .sector_price_sources_v3 import manifest_load
from .krw_fx_v5 import build_entry_dates,attach_fx
from .krw_detail_regime_v5 import fx_daily_features,fx_asof_signal,FX_FEATURES

MODEL_NAME="CFM_V7_FROZEN_KRW_REGIME"
LAST_TRAIN_SESSION="2026-11-10"
FREEZE_DATE="2026-11-15"
FIRST_PROSPECTIVE="2026-11-16"
FIT_C=0.10
PROBABILITY_CUTOFF=0.55

def _package_scale_pca(columns,scale,pca,variance_standardized=False):
    return {
        "columns":list(columns),
        "scaler_mean":scale.mean_.astype(float).tolist(),
        "scaler_scale":scale.scale_.astype(float).tolist(),
        "pca_mean":pca.mean_.astype(float).tolist(),
        "pca_components":pca.components_.astype(float).tolist(),
        "pca_explained_variance":pca.explained_variance_.astype(float).tolist(),
        "variance_standardized":bool(variance_standardized)
    }

def latent_numpy(frame,block):
    columns=block["columns"]
    if not set(columns).issubset(frame.columns):
        raise ValueError("model input missing columns: "+",".join(sorted(set(columns)-set(frame))))
    a=frame[columns].astype(float).to_numpy()
    if not np.isfinite(a).all():
        raise ValueError("missing/nonfinite frozen factor values")
    mean=np.asarray(block["scaler_mean"],float)
    scale=np.asarray(block["scaler_scale"],float)
    pca_mean=np.asarray(block["pca_mean"],float)
    comps=np.asarray(block["pca_components"],float)
    if scale.size!=a.shape[1] or comps.shape[1]!=a.shape[1]:
        raise ValueError("frozen model dimension mismatch")
    if (scale<=0).any():raise ValueError("invalid frozen scaler")
    z=np.clip((a-mean)/scale,-8,8)
    result=(z-pca_mean)@comps.T
    if block["variance_standardized"]:
        var=np.asarray(block["pca_explained_variance"],float)
        result=result/np.sqrt(np.maximum(var,1e-12))
    return result

def score_frozen_json(frame,model):
    if model.get("model")!=MODEL_NAME or model.get("promotion_allowed") is not False:
        raise ValueError("model provenance or LIVE safety flag invalid")
    if frame.empty:
        return np.array([],dtype=float)
    if "date" not in frame or frame.date.astype(str).lt(FIRST_PROSPECTIVE).any():
        # Historical roundtrip testing bypasses this *outside* this function
        # using _score_matrix to avoid accidentally presenting it as prospective.
        raise ValueError("prospective score requested before frozen model launch")
    return _score_matrix(frame,model)

def _score_matrix(frame,model):
    if not set(FEATURES).issubset(frame.columns):
        raise ValueError("not all 20 technical features available")
    if not set(MACRO_COLS).issubset(frame.columns):
        raise ValueError("not all 10 ETF macro features available")
    if not set(FX_FEATURES).issubset(frame.columns):
        raise ValueError("FX features missing")
    group=np.column_stack([latent_numpy(frame,b) for b in model["technical_blocks"]])
    context=np.column_stack([
        (frame.event=="DOWN_RALLY").astype(float).to_numpy(),
        (frame.event=="SIDE_DIP").astype(float).to_numpy()])
    etf=latent_numpy(frame,model["macro_etf"])
    fx=latent_numpy(frame,model["krw_fx"])
    highvol=(frame.qqq_atr_pct.astype(float).to_numpy()>
             float(model["high_vol_cutoff"])).astype(float)[:,None]
    matrix=np.column_stack([group,context,etf,fx,highvol])
    coef=np.asarray(model["classifier_coef"],dtype=float)
    intercept=float(model["classifier_intercept"])
    if matrix.shape[1]!=coef.size:
        raise ValueError("frozen logistic dimension mismatch")
    logit=matrix@coef+intercept
    return np.exp(-np.logaddexp(0,-logit))

def validate_frozen_integrity(model):
    if model.get("prospective_starts")!=FIRST_PROSPECTIVE:
        raise ValueError("frozen start mismatch")
    if model.get("training_last_session")!=LAST_TRAIN_SESSION:
        raise ValueError("training cutoff mismatch")
    if model.get("promotion_allowed") is not False or not model.get("no_retraining"):
        raise ValueError("LIVE or retraining prohibited")
    if len(model.get("raw_technical_features",[]))!=20:
        raise ValueError("lost source indicator columns")
    used=[item for block in model["technical_blocks"] for item in block["columns"]]
    if sorted(used)!=sorted(FEATURES):raise ValueError("not all raw features accounted for")
    if len(model["macro_etf"]["columns"])!=len(MACRO_COLS):
        raise ValueError("lost ETF factors")
    if len(model["krw_fx"]["columns"])!=len(FX_FEATURES):
        raise ValueError("lost FX factors")
    if model["max_training_exit_date"]>LAST_TRAIN_SESSION:
        raise ValueError("outcome lookahead past frozen source date")
    if model["model"]!=MODEL_NAME:raise ValueError("unknown model type")
    return True

def freeze_model(manifest,stock_prices,tech_history,signal_events,
                 macro_etf,fx,source_hashes=None):
    """No partially known outcomes: use labels with end dates <= Nov10 ONLY."""
    if signal_events.empty:raise ValueError("no training event labels")
    if set(stock_prices)!={a["symbol"] for a in manifest["universe"] if a["model_eligible"]}:
        raise ValueError("not all 14 target stocks loaded")
    if fx.date.max()!=LAST_TRAIN_SESSION or macro_etf.date.max()!=LAST_TRAIN_SESSION:
        raise ValueError("data past or earlier than frozen source date")
    for symbol,data in stock_prices.items():
        if str(data.date.max())!=LAST_TRAIN_SESSION:
            raise ValueError(f"{symbol}: unexpected last frozen stock session")
    if (signal_events.date>LAST_TRAIN_SESSION).any():
        raise ValueError("training inputs from beyond freeze")
    events=signal_events.loc[(signal_events.exit_date<=LAST_TRAIN_SESSION)].copy()
    if (events.exit_date>LAST_TRAIN_SESSION).any():raise ValueError("future trade labels")
    if len(events)<500:raise ValueError("insufficient training events")
    positions=build_entry_dates(events,stock_prices)
    values=attach_fx(positions,fx)
    values=values.merge(macro_etf,on="date",how="left",validate="many_to_one")
    fxrows=fx_asof_signal(values.date,fx)
    for col in FX_FEATURES:
        values[col]=fxrows[col].to_numpy(float)
    if values[list(FEATURES)+list(MACRO_COLS)+list(FX_FEATURES)].isna().any().any():
        raise ValueError("incomplete training factors")
    labels=(values.krw_mark_return>0).astype(int)
    if min(int(labels.sum()),int((1-labels).sum()))<100:
        raise ValueError("KRW target not sufficiently balanced")
    context=tech_history[(tech_history.date_ny<=LAST_TRAIN_SESSION)].dropna(
        subset=list(FEATURES))
    if context.empty or context.date_ny.max()>LAST_TRAIN_SESSION:
        raise ValueError("missing clean feature histories")
    tech=FullCoverageFactorTransformer().fit(context)
    etf=MacroPCA().fit(macro_etf[macro_etf.date<=LAST_TRAIN_SESSION].dropna(
        subset=list(MACRO_COLS)))
    fx_features=fx_daily_features(fx)
    fx_past=fx_features[fx_features.date<=LAST_TRAIN_SESSION].dropna(
        subset=list(FX_FEATURES))
    fx_scaler=StandardScaler().fit(fx_past[list(FX_FEATURES)])
    fx_pca=PCA(n_components=2,svd_solver="full").fit(np.clip(
        fx_scaler.transform(fx_past[list(FX_FEATURES)]),-8,8))
    vol_threshold=float(context.qqq_atr_pct.quantile(.75))
    columns=np.column_stack([
      _input_latent(tech,values),
      etf.transform(values),
      fx_pca.transform(np.clip(
         fx_scaler.transform(values[list(FX_FEATURES)]),-8,8)),
      (values.qqq_atr_pct.astype(float)>vol_threshold).astype(float).to_numpy()])
    cls=LogisticRegression(C=FIT_C,max_iter=1800)
    cls.fit(columns,labels)
    if list(cls.classes_)!=[0,1]:
        raise ValueError("incompatible frozen positive class")
    tech_blocks=[
      _package_scale_pca(columns,scale,pca,variance_standardized=True)
      for columns,scale,pca in zip(tech.blocks,tech.scalers,tech.pcas)]
    model={"model":MODEL_NAME,"frozen_on":FREEZE_DATE,
        "prospective_starts":FIRST_PROSPECTIVE,
        "training_last_session":LAST_TRAIN_SESSION,
        "max_training_exit_date":str(values.exit_date.max()),
        "training_event_count":len(values),
        "winning_krw_labels":int(labels.sum()),
        "losing_or_zero_krw_labels":int((1-labels).sum()),
        "raw_technical_features":list(FEATURES),
        "technical_blocks":tech_blocks,
        "macro_etf":_package_scale_pca(MACRO_COLS,etf.scale,etf.pca),
        "krw_fx":_package_scale_pca(FX_FEATURES,fx_scaler,fx_pca),
        "high_vol_cutoff":vol_threshold,
        "classifier_coef":cls.coef_[0].astype(float).tolist(),
        "classifier_intercept":float(cls.intercept_[0]),
        "probability_threshold":PROBABILITY_CUTOFF,
        "source_price_provenance":source_hashes or {},
        "training_window_revisited":True,
        "outcomes_only_completed_before_frozen_date":True,
        "no_retraining":True,
        "promotion_allowed":False,
        "broker_fx_execution_verified":False,
        "note":"First prospective model observation no earlier than 2026-11-16 NYSE close. Source price vintage is newly frozen, not a continuation of older artifact data."}
    validate_frozen_integrity(model)
    reference=cls.predict_proba(columns)[:,1]
    ported=_score_matrix(values,model)
    err=float(np.max(abs(reference-ported)))
    if err>1e-10:
        raise ValueError(f"JSON numerical implementation diverged: {err}")
    return model,{"training_event_count":len(values),
                  "model_training_max_abs_probability_diff":err,
                  "prospective_eligible_after":FIRST_PROSPECTIVE,
                  "source_vintage_changed_relative_to_v6":True,
                  "promotion_allowed":False}

def freeze_from_archive(data_dir,manifest_path,output):
    root=Path(data_dir)
    manifest=manifest_load(manifest_path)
    market={a["symbol"]:pd.read_csv(root/f"{a['symbol']}.csv")
            for a in manifest["universe"] if a["asset_class"]!="CRYPTO"}
    stocks,history,events,holds=panel_from_sources(manifest,root)
    if holds or len(stocks)!=14:raise ValueError("incomplete 14-stock source")
    macro=macro_history({s:market[s] for s in MACRO_ETFS})
    fx=pd.read_csv(Path(output).parent/"krw_fx_v5"/"usdkrw_public_daily.csv")
    return freeze_model(manifest,stocks,history,events,macro,fx)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-dir",default="results/regime_countertrend/universe_v3_prices")
    parser.add_argument("--manifest",default="research/regime_countertrend/universe_sector_v3.json")
    parser.add_argument("--fx",default="results/regime_countertrend/krw_fx_v5/usdkrw_public_daily.csv")
    parser.add_argument("--out",default="results/regime_countertrend/frozen_v7")
    args=parser.parse_args()
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    manifest=manifest_load(args.manifest)
    market={a["symbol"]:pd.read_csv(Path(args.source_dir)/f"{a['symbol']}.csv")
            for a in manifest["universe"] if a["asset_class"]!="CRYPTO"}
    stocks,history,events,holds=panel_from_sources(manifest,args.source_dir)
    if holds or len(stocks)!=14:raise ValueError("not all stock prices available")
    fx=pd.read_csv(args.fx)
    macro=macro_history({s:market[s] for s in MACRO_ETFS})
    fx_anchor=fx.loc[fx.date==LAST_TRAIN_SESSION,"usdkrw_close"]
    if len(fx_anchor)!=1:raise ValueError("missing frozen USDKRW anchor")
    vintages={}
    for ticker,source in market.items():
        ticker_anchor=source.loc[source.date==LAST_TRAIN_SESSION,"close"]
        if len(ticker_anchor)!=1:raise ValueError("missing freeze anchor "+ticker)
        checkpoints={}
        for date in ("2019-12-31","2022-12-30","2024-12-31",LAST_TRAIN_SESSION):
            v=source.loc[source.date==date,"close"]
            if len(v)==1:checkpoints[date]=float(v.iloc[0])
        vintages[ticker]={"last_close_usd":float(ticker_anchor.iloc[0]),
            "historical_checkpoints":checkpoints,
            "source_csv_sha256":hashlib.sha256(
                (Path(args.source_dir)/f"{ticker}.csv").read_bytes()).hexdigest()}
    source_hashes={"source_vintage_name":"NEW_FROZEN_NOV_15_NOT_V5_NOV_11",
        "last_observed_price_date":LAST_TRAIN_SESSION,
        "anchors":vintages,
        "usdkrw_last_close":float(fx_anchor.iloc[0]),
        "fx_csv_sha256":hashlib.sha256(Path(args.fx).read_bytes()).hexdigest()}
    model,report=freeze_model(manifest,stocks,history,events,macro,fx,
                              source_hashes=source_hashes)
    if len(model["source_price_provenance"]["anchors"])!=24:
        raise ValueError("frozen model is missing asset provenance")
    model_json=json.dumps(model,sort_keys=True,separators=(",",":"),allow_nan=False)
    (root/"cfm_v7_frozen_krw_model.json").write_text(model_json+"\n")
    sha=hashlib.sha256((model_json+"\n").encode()).hexdigest()
    report.update({"json_model_sha256":sha,
      "source_last_session":LAST_TRAIN_SESSION,
      "frozen_created_on":FREEZE_DATE,
      "hold_reason":"Independent future performance and broker fills not available.",
      "model_json_not_committed_until_verified":True})
    (root/"freeze_validation.json").write_text(
         json.dumps(report,indent=2,ensure_ascii=False))
    print("CFM_V7_FROZEN",json.dumps(report))
if __name__=="__main__":
    main()
