"""Fixed causal local-linear Kalman vs matched EMA on the frozen Daily20 archive.

Research only. The three added features and filter parameters are one fixed
challenger, not an exhaustive search or the production Kalman implementation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, FEATURES, KEY, ASOF, load_archive, load_original, csv, normalize_keys

KALMAN=["kf_gap","kf_slope","kf_slope_change5"]
EMA=["ema_gap","ema_slope","ema_slope_change5"]
CORE=["SPY","QQQ","QLD","IWM","AAPL","MSFT","AMZN","GOOGL","META","NVDA","AMD","AVGO","MU","TSLA","PLTR","IONQ","COIN","MSTR","JPM","XOM"]
YEARS=(2024,2025,2026)


def causal_features(close):
    if not close.index.is_unique or not close.index.is_monotonic_increasing or not np.isfinite(close).all() or not close.gt(0).all():
        raise ValueError("INVALID_CLOSE_SERIES")
    log=np.log(close.astype(float))
    A=np.array([[1.,1.],[0.,1.]])
    Q=np.diag([.01,.0001])
    I=np.eye(2); P=np.eye(2); x=np.array([log.iloc[0],0.])
    out=[]
    for i,obs in enumerate(log):
        if i:
            x=A@x; P=A@P@A.T+Q
            gain=P[:,0]/(P[0,0]+1.)
            x=x+gain*(obs-x[0])
            M=I-np.outer(gain,[1.,0.])
            P=M@P@M.T+np.outer(gain,gain)
        out.append([obs-x[0],x[1]])
    k=pd.DataFrame(out,index=close.index,columns=KALMAN[:2])
    k[KALMAN[2]]=k.kf_slope.diff(5)
    e=log.ewm(span=20,adjust=False).mean(); slope=e.diff(5)/5
    k[EMA[0]]=log-e;k[EMA[1]]=slope;k[EMA[2]]=slope.diff(5)
    k.iloc[:60]=np.nan
    return k


def model(cols, train, target, balanced):
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(SimpleImputer(strategy="median",keep_empty_features=True),
        StandardScaler(),LogisticRegression(C=.2,class_weight="balanced" if balanced else None,
                                           random_state=42,max_iter=500)).fit(train[cols],target)


def metric(y,p):
    from sklearn.metrics import roc_auc_score,brier_score_loss
    return {"n":int(len(y)),"events":int(y.sum()),
            "auc":float(roc_auc_score(y,p)) if y.nunique()==2 else None,
            "brier":float(brier_score_loss(y,p))}


def within(frame,p,y):
    from sklearn.metrics import roc_auc_score
    pairs=0;weighted=0.;groups=0
    for _,g in frame.groupby(["symbol","year"]):
        n1=int(g[y].sum());n0=len(g)-n1
        if n1 and n0:
            n=n1*n0; weighted+=n*roc_auc_score(g[y],g[p]);pairs+=n;groups+=1
    return {"auc":weighted/pairs if pairs else None,"pairs":pairs,"groups":groups}


def trades(frame,p):
    selected=[]
    for _,g in frame.groupby("symbol"):
        last=pd.Timestamp("1900-01-01")
        for row in g.sort_values("signal_date").itertuples(index=False):
            if row.signal_date<=last or getattr(row,p)<.6:
                continue
            selected.append(row);last=row.exit_date
    out=pd.DataFrame(selected)
    if out.empty:
        return out,{"n":0}
    return out,{"n":len(out),"dates":int(out.signal_date.nunique()),
        "mean_net":float(out.net_return.mean()),"win_rate":float(out.win.mean()),
        "severe_rate":float(out.severe.mean()),
        "year":{str(y):{"n":len(g),"mean_net":float(g.net_return.mean()),
                       "win_rate":float(g.win.mean())} for y,g in out.groupby("year")}}


def block_ranges(frame,calendar,y,methods):
    q=frame.copy(); base=methods[0]; comps=methods[1:]
    for m in comps:
        q[m+"_delta"]=(q[y]-q[base])**2-(q[y]-q[m])**2
    cols=[m+"_delta" for m in comps]
    agg=q.groupby("signal_date").agg(n=(y,"size"),
        **{c:(c,"sum") for c in cols}).reindex(calendar,fill_value=0).to_numpy(float)
    rng=np.random.default_rng(42);n=len(agg);out=[]
    for block in (5,20,60):
        starts=rng.integers(0,n,size=(10000,int(np.ceil(n/block))))
        ix=((starts[:,:,None]+np.arange(block))%n).reshape(10000,-1)[:,:n]
        sums=agg[ix].sum(axis=1);valid=sums[:,0]>0;v=sums[valid,1:]/sums[valid,0,None]
        out.append({"block":block,"valid":int(valid.sum()),
            "baseline_minus_challenger_brier":{m:np.quantile(v[:,i],[.025,.975]).tolist()
                                              for i,m in enumerate(comps)}})
    return out


def split(frame,year):
    cutoff=pd.Timestamp(year,1,1)
    return (frame.loc[(frame.index<cutoff)&frame.exit_date.lt(cutoff)],
            frame.loc[frame.index.year==year].copy())


def run_ablation(frames,columns,calendar):
    variants={"base":list(columns),"kalman":list(columns)+KALMAN,"ema":list(columns)+EMA}
    predictions=[];folds=[]
    for s in CORE:
        f=frames[s].copy();f=f.loc[f.net_return.notna()].copy()
        f["win"]=f.net_return.gt(0).astype(int);f["severe"]=f.net_return.le(-.05).astype(int)
        for y in YEARS:
            tr,te=split(f,y)
            if len(tr)<252 or len(te)<10 or tr.win.nunique()<2:
                continue
            # Original train split, completed labels, fixed per-symbol model/gate.
            for m,cols in variants.items():
                te[m+"_win"]=model(cols,tr,tr.win,True).predict_proba(te[cols])[:,1]
                te[m+"_severe"]=model(cols,tr,tr.severe,False).predict_proba(te[cols])[:,1] if tr.severe.nunique()==2 else tr.severe.mean()
            te["severe_prior"]=tr.severe.mean()
            te["symbol"]=s;te["year"]=y;te["signal_date"]=te.index
            allowed=te.spy_above200_lag.ge(.5)&te.vix_lag.le(35.)
            folds.append({"symbol":s,"year":y,"train_n":len(tr),"test_n":len(te),"bull_n":int(allowed.sum())})
            predictions.append(te.loc[allowed])
    p=pd.concat(predictions,ignore_index=True)
    if p.duplicated(["symbol","signal_date"]).any():
        raise ValueError("DUPLICATE_SCORE")
    if p[KALMAN+EMA].isna().any().any():
        raise ValueError("MISSING_EVAL_CHALLENGER")
    if len(folds)!=60 or len(p)!=13120 or p.signal_date.nunique()!=656:
        raise ValueError("FROZEN_EVALUATION_COVERAGE_MISMATCH")
    out={"folds":folds,"eligible_n":len(p),"distinct_dates":int(p.signal_date.nunique()),
         "metrics":{},"trades":{},"descriptive_block_ranges":{}}
    for target in ("win","severe"):
        methods=[m+"_"+target for m in variants]+(["severe_prior"] if target=="severe" else [])
        out["metrics"][target]={m:{"pooled":metric(p[target],p[m]),
            "within_symbol_year":within(p,m,target),
            "annual":{str(y):metric(g[target],g[m]) for y,g in p.groupby("year")}} for m in methods}
        cal=calendar[(calendar>=pd.Timestamp("2024-01-01"))&(calendar<=pd.Timestamp(ASOF))]
        out["descriptive_block_ranges"][target]=block_ranges(p,cal,target,methods[:3])
    for m in variants:
        _,out["trades"][m]=trades(p,m+"_win")
    return out,p


def run(raw,result,train):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name,blob in raw.items():
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
        market=root/"market";features=root/"features"
        context=train.context_frame(market)
        calendar=train.load_bars(train.market_file(market,"SPY")).index
        frames={}
        for s in CORE:
            b=train.load_bars(train.market_file(market,s))
            frames[s]=train.feature_frame(s,market,features,context,20.).join(causal_features(b.close))
        out,p=run_ablation(frames,FEATURES,calendar)
    original=csv(result,"research/oos_trades.csv")
    original=normalize_keys(original.loc[original.strategy.eq("LOGISTIC")])
    replayed,_=trades(p,"base_win")
    a=original.merge(replayed[KEY+["base_win"]],on=KEY,how="outer",indicator=True,validate="one_to_one")
    audit={"archived":len(original),"replayed":len(replayed),"matched":int(a._merge.eq("both").sum()),
           "old_only":int(a._merge.eq("left_only").sum()),"new_only":int(a._merge.eq("right_only").sum()),
           "max_score_abs_diff":float((a.probability-a.base_win).abs().max())}
    if audit["matched"]!=439 or audit["old_only"] or audit["new_only"] or audit["max_score_abs_diff"]>2e-6:
        raise ValueError("ORIGINAL_BASELINE_REPLAY_MISMATCH")
    import sklearn,pyarrow
    return {"schema":"kalman-local-linear-ablation-v1","research_only":True,
            "approved_live":False,"production_writes":False,"new_holdout":False,
            "source_finality_certified":False,"portfolio_resimulated":False,
            "input_sha256":{k:v[2] for k,v in ARCHIVES.items()},
            "runtime_versions":{"numpy":np.__version__,"pandas":pd.__version__,
                "sklearn":sklearn.__version__,"pyarrow":pyarrow.__version__},
            "asof":ASOF,"original_baseline_replay":audit,
            "fixed_filter":{"state":"log_price_and_slope","q_diagonal":[.01,.0001],
                "r":1.,"initial_covariance":"identity","warmup_sessions":60,"ema_span":20},
            "limitations":["Inspected historical OOS; no independent holdout or causal inference.",
                "One fixed Kalman challenger, not all filter variants or a production filter audit.",
                "Original fixed universe and price/listing provenance remain HOLD.",
                "All eligible labels overlap; date-block resampling is descriptive, not confirmatory.",
                "Nonoverlapping candidate summaries are not cash-ledger portfolio returns.",
                "Bull regime only; no Bear result or rule promotion."],**out}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    for name in ("data","results","original-source","out"):
        parser.add_argument("--"+name,required=True)
    a=parser.parse_args()
    report=run(load_archive(a.data,"data"),load_archive(a.results,"results"),load_original(a.original_source))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("KALMAN_ABLATION_RESEARCH_ONLY",report["eligible_n"],report["original_baseline_replay"])
