from __future__ import annotations
import argparse, gc, hashlib, json, math, os, resource
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE="R5C0_HGB_REFERENCE"; COST=.001; HORIZONS=(2,4,6,8); COVERAGES=(.25,.50,.75)
CORE=["base_score","margin2","margin6","score_z","score_sd","weight","cs_ret_1b","cs_ret_2b","cs_ret_4b","cs_ret_6b","cs_rv_6","cs_rv_24","cs_ma_dist_6","cs_ma_dist_24","cs_volume_z_24","cs_bar_range","cs_beta24","cs_residual_ret_6b"]
CTX=["universe_median_rv24","qqq_ret_2b","qqq_ret_6b","qqq_rv_24","qqq_ma_dist_24","ix_trend_qqq","ix_vol_qqq","ix_ret1_qqq","ix_mom6_qqq"]
DERIVED={"base_score","margin2","margin6","score_z","score_sd","weight"}
FORBID=("fwd","future","target","relative_ret","universe_mean_ret","universe_median_ret","qqq_fwd")
REQ={"timestamp","target_timestamp_4b","expected_seq","symbol","fold","fwd_ret_4b","rv_24","universe_median_rv24",BASE}

def args():
    p=argparse.ArgumentParser(); root=os.getenv("KALMAN_DATA_ROOT","/mnt/gdrive")
    p.add_argument("--scored",default=f"{root}/US_ETF/model_lab_v1/results/r5_0_1_research_sandbox_all_data/r5_0_1_scored_rows.parquet")
    p.add_argument("--panel",default=f"{root}/US_ETF/directional_research/canonical_history_v1/panel_1h_gap_aware")
    p.add_argument("--out",default=f"{root}/US_ETF/model_lab_v1/results/r6_selective_horizon")
    p.add_argument("--min-universe",type=int,default=80); p.add_argument("--min-train",type=int,default=250)
    p.add_argument("--bootstrap",type=int,default=2000); p.add_argument("--dry-run",action="store_true")
    return p.parse_args()

def mem(stage):
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    print(f"[R6] {stage} rss_max_mb={rss:.1f}",flush=True)

def utc(x): return pd.to_datetime(x,utc=True,errors="coerce")
def sf(x,d=np.nan):
    try:
        v=float(x); return v if np.isfinite(v) else d
    except Exception: return d

def mdd(r):
    r=np.asarray(r,float)
    if not len(r): return np.nan
    e=np.r_[1.,np.cumprod(1+r)]; return float(np.min(e/np.maximum.accumulate(e)-1))
def metrics(t):
    if t.empty: return dict(trades=0,cum_return=0.,log_growth=0.,avg_return=np.nan,median_return=np.nan,win_rate=np.nan,profit_factor=np.nan,max_drawdown=np.nan)
    r=pd.to_numeric(t.net_return,errors="coerce").dropna().to_numpy(float); pos=r[r>0].sum(); neg=-r[r<0].sum()
    return dict(trades=len(r),cum_return=float(np.prod(1+r)-1),log_growth=float(np.log1p(r).sum()),avg_return=float(r.mean()),median_return=float(np.median(r)),win_rate=float((r>0).mean()),profit_factor=float(pos/neg) if neg else np.inf,max_drawdown=mdd(r))

def projected_scored(path):
    pf=pq.ParquetFile(path)
    available=set(pf.schema.names)
    wanted=REQ | {c for c in CORE+CTX if c not in DERIVED}
    missing=REQ-available
    if missing: raise ValueError(f"missing R5 columns: {sorted(missing)}")
    cols=sorted(wanted & available)
    print(f"[R6] parquet_rows={pf.metadata.num_rows} projected_columns={len(cols)}/{len(available)}",flush=True)
    frame=pd.read_parquet(path,columns=cols)
    for c in ("symbol","fold"):
        if c in frame: frame[c]=frame[c].astype("category")
    mem("PROJECTED_R5_LOADED")
    return frame,int(pf.metadata.num_rows),cols

def top1(sc,min_u):
    z=sc
    z["timestamp"]=utc(z.timestamp); z["target_timestamp_4b"]=utc(z.target_timestamp_4b); z["expected_seq"]=pd.to_numeric(z.expected_seq,errors="coerce")
    z=z.dropna(subset=list(REQ)); z["expected_seq"]=z.expected_seq.astype("int64")
    passcols=[c for c in set(CORE+CTX) if c in z and c not in DERIVED]
    out=[]
    for ts,g in z.groupby("timestamp",sort=True,observed=True):
        if len(g)<min_u: continue
        g=g.sort_values([BASE,"symbol"],ascending=[False,True])
        s=pd.to_numeric(g[BASE],errors="coerce").dropna().to_numpy(float)
        if len(s)<min_u: continue
        a=g.iloc[0]; sd=float(np.std(s,ddof=1)); rv=sf(a.rv_24); mr=sf(a.universe_median_rv24); w=float(np.clip(mr/rv,.25,1.)) if rv>0 and np.isfinite(mr) else 1.
        d={"timestamp":ts,"target_timestamp_4b":a.target_timestamp_4b,"expected_seq":int(a.expected_seq),"symbol":str(a.symbol),"fold":str(a.fold),"base_score":float(s[0]),"margin2":float(s[0]-s[1]),"margin6":float(s[0]-s[5]),"score_z":float((s[0]-s.mean())/sd) if sd>0 else 0.,"score_sd":sd,"weight":w,"fwd_ret_4b":float(a.fwd_ret_4b)}
        d["net_ret_4b"]=w*d["fwd_ret_4b"]-w*COST; d["label"]=int(d["net_ret_4b"]>0)
        for c in passcols: d[c]=a[c]
        out.append(d)
    ret=pd.DataFrame(out).sort_values("timestamp").reset_index(drop=True)
    mem("TOP1_COMPRESSED")
    return ret

def horizons(d,panel):
    d=d.copy(); audit={}
    for h in HORIZONS: d[f"net_ret_{h}b"]=np.nan
    for sym,idx in d.groupby("symbol").groups.items():
        p=panel/f"{sym}_1h_gap_aware.parquet"
        try: q=pd.read_parquet(p,columns=["expected_seq","close"])
        except Exception as e: audit[sym]={"status":"FAIL","error":str(e)}; continue
        q=q.dropna(); q.expected_seq=pd.to_numeric(q.expected_seq).astype("int64"); close=q.drop_duplicates("expected_seq",keep="last").set_index("expected_seq").close.astype(float)
        seq=d.loc[idx,"expected_seq"].to_numpy(int); ent=close.reindex(seq).to_numpy(float); w=d.loc[idx,"weight"].to_numpy(float)
        for h in HORIZONS:
            ex=close.reindex(seq+h).to_numpy(float); ret=ex/ent-1; d.loc[idx,f"net_ret_{h}b"]=w*ret-w*COST
        audit[sym]={"status":"READY","rows":len(idx)}
        del q,close,seq,ent,w
    gc.collect(); mem("HORIZONS_READY")
    x=d.net_ret_4b.copy(); d["canonical_net_ret_4b"]=x; d["net_ret_4b"]=d.weight*d.fwd_ret_4b-d.weight*COST
    dif=(d.canonical_net_ret_4b-d.net_ret_4b).abs().dropna(); audit["_4h_parity"]={"n":len(dif),"median_abs_diff":float(dif.median()) if len(dif) else None,"max_abs_diff":float(dif.max()) if len(dif) else None}
    return d,audit

def feats(d,context):
    f=[x for x in CORE+(CTX if context else []) if x in d]
    bad=[x for x in f if any(t in x.lower() for t in FORBID)]
    if bad: raise RuntimeError(f"leakage features: {bad}")
    return f

def crossfit(d,context,min_train):
    f=feats(d,context); order=d.groupby("fold").timestamp.min().sort_values().index.astype(str); outs=[]; info=[]
    for fold in order:
        te=d[d.fold.astype(str)==fold].copy(); start=te.timestamp.min(); tr=d[d.target_timestamp_4b<start].sort_values("timestamp").copy()
        if len(tr)<min_train or tr.label.nunique()<2: continue
        ncal=min(max(80,math.ceil(len(tr)*.25)),max(30,len(tr)//3)); core=tr.iloc[:-ncal]; cal=tr.iloc[-ncal:]
        pipe=Pipeline([("imp",SimpleImputer(strategy="median")),("sc",StandardScaler()),("lr",LogisticRegression(C=.2,max_iter=3000,random_state=42))]); pipe.fit(core[f],core.label)
        pc=pipe.predict_proba(cal[f])[:,1]; pt=pipe.predict_proba(te[f])[:,1]; method="logit"
        if cal.label.nunique()>1 and len(np.unique(np.round(pc,10)))>=10:
            iso=IsotonicRegression(y_min=.01,y_max=.99,out_of_bounds="clip").fit(pc,cal.label); pc=iso.predict(pc); pt=iso.predict(pt); method="logit+isotonic"
        te["p_meta"]=pt
        th={}
        for cov in COVERAGES:
            v=float(np.quantile(pc,1-cov)); th[int(cov*100)]=v; te[f"select_{int(cov*100):02d}"]=te.p_meta>=v
        te["context_model"]=context; outs.append(te); info.append({"fold":fold,"train":len(tr),"core":len(core),"cal":len(cal),"test":len(te),"method":method,"threshold50":th[50]})
        del tr,core,cal,pipe,pc,pt
        gc.collect()
    if not outs: raise RuntimeError("no meta OOS folds")
    mem("META_CROSSFIT_CONTEXT" if context else "META_CROSSFIT_CORE")
    return pd.concat(outs,ignore_index=True).sort_values("timestamp"),info

def sim(d,h=4,sel=None,hcol=None):
    z=d.sort_values(["expected_seq","timestamp"]); z=z[z[sel].fillna(False)] if sel else z; out=[]; free=-10**18
    for _,r in z.iterrows():
        seq=int(r.expected_seq)
        if seq<free: continue
        hh=int(r[hcol]) if hcol else h; val=sf(r.get(f"net_ret_{hh}b"))
        if not np.isfinite(val): continue
        x=r.to_dict(); x.update(horizon=hh,net_return=val,exit_expected_seq=seq+hh); out.append(x); free=seq+hh
    return pd.DataFrame(out)

def fold_order(*fs):
    common=set(fs[0].fold.astype(str).unique())
    for f in fs[1:]: common&=set(f.fold.astype(str).unique())
    first={k:min(f[f.fold.astype(str)==k].timestamp.min() for f in fs) for k in common}; return sorted(common,key=first.get)
def choose_h(d,fold):
    start=d[d.fold.astype(str)==fold].timestamp.min(); tr=d[d.timestamp<start]; ms={h:metrics(sim(tr,h)) for h in HORIZONS}
    return max(HORIZONS,key=lambda h:(ms[h]["log_growth"] if np.isfinite(ms[h]["log_growth"]) else -np.inf,h==4,-abs(h-4))),ms
def assign_h(test,hist,order):
    out=[]; log=[]
    for fold in order:
        z=test[test.fold.astype(str)==fold].copy(); h,ms=choose_h(hist,fold); z["wf_horizon"]=h; out.append(z); log.append({"fold":fold,"horizon":h,"train_metrics":ms})
    return pd.concat(out,ignore_index=True),log

def daily(t):
    if t.empty:return pd.Series(dtype=float)
    z=t.copy(); z["date"]=utc(z.timestamp).dt.floor("D"); z["lr"]=np.log1p(z.net_return); return z.groupby("date").lr.sum()
def boot(base,cand,reps):
    a=daily(base); b=daily(cand); ix=a.index.union(b.index).sort_values(); diff=b.reindex(ix,fill_value=0).to_numpy()-a.reindex(ix,fill_value=0).to_numpy(); n=len(diff)
    if n<20:return {"days":n,"ci95_low":None,"ci95_high":None,"p":None}
    rng=np.random.default_rng(42); block=5; starts=np.arange(max(1,n-block+1)); vals=np.empty(reps,float)
    nb=math.ceil(n/block)
    for i in range(reps):
        picks=rng.choice(starts,size=nb,replace=True)
        s=np.concatenate([diff[j:j+block] for j in picks])[:n]
        vals[i]=np.mean(s)
    return {"days":n,"mean":float(diff.mean()),"ci95_low":float(np.quantile(vals,.025)),"ci95_high":float(np.quantile(vals,.975)),"p":float((np.sum(vals<=0)+1)/(len(vals)+1))}

def main():
    a=args(); scored=Path(a.scored); panel=Path(a.panel); out=Path(a.out)
    if os.getenv("R6_ALLOW_LIVE","").lower()=="true": raise RuntimeError("R6 research refuses live mode")
    if not scored.exists() or not panel.exists(): raise FileNotFoundError(f"missing input: {scored} / {panel}")
    mem("START")
    sc,input_rows,projected=projected_scored(scored)
    d=top1(sc,a.min_universe)
    del sc; gc.collect(); mem("R5_FRAME_RELEASED")
    d,audit=horizons(d,panel)
    core,ci=crossfit(d,False,a.min_train); ctx,xi=crossfit(d,True,a.min_train); order=fold_order(core,ctx)
    if len(order)<3: raise RuntimeError(f"too few common meta folds: {order}")
    eligible=d[d.fold.astype(str).isin(order)]; core=core[core.fold.astype(str).isin(order)]; ctx=ctx[ctx.fold.astype(str).isin(order)]
    arms={"R5_BASE_4H":sim(eligible,4),"R6A_CORE_SELECTIVE50_4H":sim(core,4,"select_50"),"R6A_CONTEXT_SELECTIVE50_4H":sim(ctx,4,"select_50"),"R6_DIAG_CONTEXT_SELECTIVE25_4H":sim(ctx,4,"select_25"),"R6_DIAG_CONTEXT_SELECTIVE75_4H":sim(ctx,4,"select_75")}
    ca,ch=assign_h(core,d,order); xa,xh=assign_h(ctx,d,order); arms["R6B_CORE_SELECTIVE50_WF_HORIZON"]=sim(ca,sel="select_50",hcol="wf_horizon"); arms["R6C_CONTEXT_SELECTIVE50_WF_HORIZON"]=sim(xa,sel="select_50",hcol="wf_horizon")
    rows=[]; folds=[]; bs={}
    for name,t in arms.items():
        m=metrics(t); m["arm"]=name; rows.append(m)
        for f,z in t.groupby("fold") if not t.empty else []: folds.append({"arm":name,"fold":str(f),**metrics(z)})
        if name!="R5_BASE_4H": bs[name]=boot(arms["R5_BASE_4H"],t,a.bootstrap)
    M=pd.DataFrame(rows); F=pd.DataFrame(folds); base=M[M.arm=="R5_BASE_4H"].iloc[0]; name="R6C_CONTEXT_SELECTIVE50_WF_HORIZON"; pri=M[M.arm==name].iloc[0]
    diffs=[]
    for f in order:
        b=F[(F.arm=="R5_BASE_4H")&(F.fold==f)]; c=F[(F.arm==name)&(F.fold==f)]
        if len(b) and len(c): diffs.append(float(c.iloc[0].log_growth-b.iloc[0].log_growth))
    checks={"trades>=300":bool(pri.trades>=300),"log_growth>base":bool(pri.log_growth>base.log_growth),"profit_factor>=base":bool(pri.profit_factor>=base.profit_factor),"win_rate>=base":bool(pri.win_rate>=base.win_rate),"mdd_within_2pp":bool(pri.max_drawdown>=base.max_drawdown-.02),"positive_folds>=5":bool(sum(x>0 for x in diffs)>=min(5,len(diffs))),"bootstrap_ci_low>0":bool(sf(bs[name].get("ci95_low"),-np.inf)>0)}
    report={"schema":"kalman-r6-selective-horizon-v1","research_only":True,"production_write":False,"toss_execution":False,"neon_write":False,"base_model":"R5.1_BASE_HGB","input_rows":input_rows,"projected_columns":projected,"top1_decisions":len(d),"meta_oos_folds":order,"horizons":HORIZONS,"cost_rate":COST,"horizon_audit":audit,"core_meta":ci,"context_meta":xi,"core_horizon":ch,"context_horizon":xh,"metrics":M.to_dict("records"),"bootstrap":bs,"primary":name,"promotion_checks":checks,"promotion_eligible":all(checks.values())}
    print(json.dumps({"status":"READY","primary":name,"promotion_eligible":report["promotion_eligible"],"metrics":report["metrics"]},indent=2,default=str))
    if not a.dry_run:
        out.mkdir(parents=True,exist_ok=True); M.to_csv(out/"r6_metrics.csv",index=False); F.to_csv(out/"r6_fold_metrics.csv",index=False); core.to_csv(out/"r6_core_meta_oos.csv",index=False); ctx.to_csv(out/"r6_context_meta_oos.csv",index=False); (out/"r6_research_report.json").write_text(json.dumps(report,indent=2,default=str)+"\n")
        (out/"r6_manifest.json").write_text(json.dumps({"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"research_only":True,"source":str(scored),"panel":str(panel),"projected_columns":projected},indent=2)+"\n")
    mem("COMPLETE")
    return 0
if __name__=="__main__": raise SystemExit(main())
