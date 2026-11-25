"""Frozen historical score diagnostics only; no orders, journal or source writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

ANALYSIS_SHA = "8a59f44532e81a2e214607982152427c2eb6011d"
ORIGINAL_SHA = "06c66c0fea6de93eeb581ce856d648d24c0ff942"
CORE = "SPY QQQ QLD IWM AAPL MSFT AMZN GOOGL META NVDA AMD AVGO MU TSLA PLTR IONQ COIN MSTR JPM XOM".split()
HIGH_RISK = {"QLD", "IONQ", "COIN", "MSTR"}
SEMIS = {"AMD", "AVGO", "MU", "NVDA"}
YEARS = (2024, 2025, 2026)
EPS = 1e-8


def verify_checkout(path, sha):
    path = Path(path).resolve()
    got = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if got != sha:
        raise ValueError("PINNED_CODE_MISMATCH")
    # Reject modified tracked files; untracked bytecode does not affect the commit.
    if subprocess.check_output(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("TRACKED_SOURCE_MODIFIED")
    return path


def gate(frame, family):
    if family == "BULL":
        return frame.spy_above200_lag.ge(.5) & frame.vix_lag.le(35)
    if family == "BEAR":
        return frame.spy_above200_lag.lt(.5) & frame.vix_lag.gt(0) & frame.vix_lag.le(45)
    raise ValueError("UNKNOWN_FAMILY")


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1-EPS)
    return np.log(p/(1-p))


def prior_correct(p, prior):
    # Analytic class-prior correction, not a guaranteed calibrated posterior.
    z = logit(p) + logit(prior)
    return 1/(1+np.exp(-z))


def historical_calibration_rows(frame, year):
    boundary = pd.Timestamp(f"{year}-01-01")
    return frame.loc[(frame.year < year) & (frame.signal_date < boundary) &
                     (frame.exit_date < boundary)].copy()


def calibrate(frame, year):
    past = historical_calibration_rows(frame, year)
    labels = past.win.astype(int)
    if len(past) < 200 or past.signal_date.nunique() < 20 or min(labels.sum(), len(labels)-labels.sum()) < 20:
        return None, {"status": "INSUFFICIENT_MATURE_HISTORY", "n": len(past),
                      "dates": int(past.signal_date.nunique())}
    est = LogisticRegression(C=1., solver="lbfgs", max_iter=500)
    est.fit(logit(past.raw).reshape(-1, 1), labels)
    return est, {"status": "PAST_OOS_ONLY", "n": len(past),
                 "dates": int(past.signal_date.nunique()),
                 "last_exit": str(past.exit_date.max().date()),
                 "slope": float(est.coef_[0, 0]), "intercept": float(est.intercept_[0])}


def metric(frame, col, probability=False):
    d = frame.loc[np.isfinite(frame[col])]
    y = d.win.astype(int)
    p = d[col].astype(float)
    out = {"n": len(d), "dates": int(d.signal_date.nunique()),
           "wins": int(y.sum()), "win_rate": float(y.mean()) if len(d) else None,
           "auc": float(roc_auc_score(y,p)) if y.nunique()==2 else None}
    num=0.; den=0
    for _,g in d.groupby("signal_date"):
        a=g.win.astype(int); n=int(a.sum())*(len(a)-int(a.sum()))
        if n:
            num+=n*roc_auc_score(a,g[col]);den+=n
    out["same_date_auc"]=float(num/den) if den else None
    out["same_date_pairs"]=den
    if probability and len(d):
        if not p.between(0,1).all():
            raise ValueError("INVALID_PROBABILITY")
        bins=[]
        for i in range(5):
            mask=(p>=i/5)&((p<(i+1)/5) if i<4 else (p<=1))
            if mask.any():
                bins.append({"bin":i,"n":int(mask.sum()),"mean_score":float(p[mask].mean()),"win_rate":float(y[mask].mean())})
        out.update(brier=float(brier_score_loss(y,p)),logloss=float(log_loss(y,np.clip(p,EPS,1-EPS),labels=[0,1])),
                   mean_score=float(p.mean()),ece_5bin=float(sum(x["n"]*abs(x["mean_score"]-x["win_rate"]) for x in bins)/len(d)),bins=bins)
    return out


def panel(train, raw, result, archive_replay):
    from regime_challenger import fit_bear_year
    rows={"BULL":[],"BEAR":[]}
    folds=[]
    prices={}
    with tempfile.TemporaryDirectory(prefix="kalman-frozen-") as tmp:
        root=Path(tmp)
        for name,blob in raw.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
        market=root/"market";features=root/"features"
        ctx=train.context_frame(market)
        for symbol in CORE:
            f=train.feature_frame(symbol,market,features,ctx,20.)
            prices[symbol]=train.load_bars(train.market_file(market,symbol)).close
            for year in range(2019,2027):
                hist,_=train.model_split(f,year)
                for family,fn in (("BULL",train.model_year),("BEAR",fit_bear_year)):
                    fitted,test,_=fn(f,year)
                    if fitted is None or test is None:
                        if year in YEARS:raise ValueError("ORIGINAL_EVAL_FOLD_ABSTENTION")
                        continue
                    eligible=gate(test,family)&test.net_return.notna()
                    q=test.loc[eligible].copy()
                    training=hist if family=="BULL" else hist.loc[gate(hist,family)]
                    hist_gate=hist.loc[gate(hist,family)]
                    train_wins=int(training.net_return.gt(0).sum())
                    train_prior=train_wins/len(training)
                    if not 0<train_prior<1:raise ValueError("TRAIN_PRIOR_INVALID")
                    symbol_prior=(int(hist_gate.net_return.gt(0).sum())+1)/(len(hist_gate)+2)
                    q["raw"]=q.prob
                    q["prior_corrected"]=prior_correct(q.prob,train_prior)
                    q["symbol_prior"]=symbol_prior
                    q["oversold_ret5"]=-q.ret5
                    q["low_rsi"]=-q.rsi14
                    q["momentum_ret1"]=q.ret1
                    q["win"]=q.net_return.gt(0).astype(int)
                    q["symbol"]=symbol;q["year"]=year
                    q["signal_date"]=q.index
                    rows[family].append(q)
                    folds.append({"family":family,"symbol":symbol,"year":year,"eligible":len(q)})
    panels={k:pd.concat(v) for k,v in rows.items()}
    audits={}
    for family,filename,kind in (("BULL","research/oos_trades.csv",None),("BEAR","research/regime_challenger/bear_oos_trades.csv","BEAR_LOGISTIC")):
        p=panels[family]
        evaluation=p.loc[p.year.isin(YEARS)]
        if evaluation.duplicated(["symbol","signal_date"]).any() or len(evaluation)!={"BULL":13120,"BEAR":980}[family]:
            raise ValueError("FROZEN_POOL_COUNT_MISMATCH")
        original=pd.read_csv(__import__("io").BytesIO(result[filename]))
        original=original.loc[original.strategy.eq("LOGISTIC")] if kind is None else original.loc[original.candidate_family.eq(kind)]
        audits[family]=archive_replay(evaluation.loc[evaluation.raw.ge(.6)],original,train)
    if sum(x["year"] in YEARS for x in folds)!=120:
        raise ValueError("FROZEN_FOLD_MISMATCH")
    return panels,prices,audits,folds


def calibration_report(panels):
    out={}
    for family,panel in panels.items():
        out[family]={}
        for name,exclude in (("PRIMARY16",HIGH_RISK),("ALL20",set())):
            f=panel.loc[~panel.symbol.isin(exclude)].copy()
            pieces=[];fits={}
            for year in YEARS:
                est,details=calibrate(f,year);fits[str(year)]=details
                q=f.loc[f.year.eq(year)].copy()
                q["temporal_sigmoid"]=np.nan if est is None else est.predict_proba(logit(q.raw).reshape(-1,1))[:,1]
                pieces.append(q)
            p=pd.concat(pieces)
            methods=("raw","symbol_prior","prior_corrected","temporal_sigmoid","oversold_ret5","low_rsi","momentum_ret1")
            prob=set(methods[:4])
            common=p.loc[p.temporal_sigmoid.notna()]
            def allmetrics(x,methods=methods):return {m:metric(x,m,m in prob) for m in methods}
            out[family][name]={"pool":allmetrics(p),"common_calibration_rows":allmetrics(common,methods[:4]),
                "annual":{str(y):allmetrics(g,methods[:4]) for y,g in p.groupby("year")},
                "calibration_fits":fits}
    return out


def correlation_report(prices,result,csv):
    """Unweighted co-holding pair-days; no causal risk or actual weight claim."""
    sessions=prices["SPY"].index
    sessions=sessions[(sessions>=pd.Timestamp("2024-01-01"))&(sessions<=pd.Timestamp("2026-11-23"))]
    if len(sessions)!=727:raise ValueError("SESSION_COUNT")
    returns=pd.DataFrame(prices).sort_index().pct_change(fill_method=None)
    cache={}
    for i,a in enumerate(sorted(CORE)):
        for b in sorted(CORE)[i+1:]:
            cache[a,b]=returns[a].rolling(60,min_periods=60).corr(returns[b]).shift(1)
    out={}
    tables=(
        ("portfolio","research/portfolio_executions.csv","research/portfolio_daily_equity.csv",("LOGISTIC","TREND_RULE")),
        ("regime","research/regime_challenger/regime_executions.csv","research/regime_challenger/regime_daily_equity.csv",("BEAR_LOGISTIC_ONLY","BULL_PLUS_BEAR_LOGISTIC","BEAR_RULE_ONLY")))
    for _,fills_name,curve_name,strategies in tables:
        fills=csv(result,fills_name);curves=csv(result,curve_name)
        fills.entry_date=pd.to_datetime(fills.entry_date);fills.exit_date=pd.to_datetime(fills.exit_date)
        curves.date=pd.to_datetime(curves.date)
        for strategy in strategies:
            for cohort in ("ALL_20","EXCLUDE_HIGH_RISK"):
                scenario=f"{strategy}__{cohort}__POS5__COST20BP"
                f=fills.loc[fills.scenario.eq(scenario)]
                c=curves.loc[curves.scenario.eq(scenario)].set_index("date").reindex(sessions)
                if f.empty or c.active_positions.isna().any():raise ValueError("SCENARIO_MISSING")
                counts=[];corrs=[];pairs=0;semi_pairs=0;multi=0;active=0
                for dt in sessions:
                    held=sorted(f.loc[(f.entry_date<=dt)&(f.exit_date>dt),"symbol"].tolist())
                    if len(held)!=len(set(held)):raise ValueError("DUPLICATE_HOLDING")
                    counts.append(len(held));active+=bool(held);multi+=len(held)>=2
                    for i,a in enumerate(held):
                        for b in held[i+1:]:
                            pairs+=1;semi_pairs+=a in SEMIS and b in SEMIS
                            x=cache[a,b].get(dt,np.nan)
                            if np.isfinite(x):corrs.append(float(x))
                if not np.array_equal(counts,c.active_positions.astype(int)):raise ValueError("ARCHIVED_ACTIVE_POSITION_MISMATCH")
                out[scenario]={"sessions":len(sessions),"active_days":active,"multi_position_days":multi,
                    "pair_days":pairs,"valid_prior60_pair_days":len(corrs),"semiconductor_pair_days":semi_pairs,
                    "mean_prior60_correlation":float(np.mean(corrs)) if corrs else None,
                    "pair_days_corr_ge_0_7":int(sum(x>=.7 for x in corrs)),
                    "average_gross_exposure":float(c.gross_exposure.mean())}
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("data","results","analysis-source","original-source","out"):
        parser.add_argument("--"+name,required=True)
    a=parser.parse_args()
    analysis=verify_checkout(a.analysis_source,ANALYSIS_SHA)
    original=verify_checkout(a.original_source,ORIGINAL_SHA)
    sys.path.insert(0,str(analysis/"research/kalman_outcome_attribution"))
    from outcome_profile import load_archive,load_original,csv,ARCHIVES
    from daily_protocol_feasibility import archive_replay
    train=load_original(original)
    raw,result=load_archive(a.data,"data"),load_archive(a.results,"results")
    panels,prices,audits,folds=panel(train,raw,result,archive_replay)
    report={"schema":"kalman-temporal-calibration-diagnostics-v1","asof":"2026-11-23",
        "research_only":True,"production_writes":False,"approved_live":False,"new_holdout":False,
        "source_finality_certified":False,"primary_study_admitted_outcomes":0,
        "analysis_source":ANALYSIS_SHA,"original_source":ORIGINAL_SHA,
        "input_sha256":{k:v[2] for k,v in ARCHIVES.items()},"payload_counts":[len(raw),len(result)],
        "fold_count":len(folds),"original_candidate_replay":audits,
        "calibration":calibration_report(panels),"coholding":correlation_report(prices,result,csv),
        "limitations":["Previously inspected historical data; fixed research diagnostics, not independent validation.",
            "Temporal calibrator only uses prior-year OOS scores with realized exits before evaluation year; overlapping labels remain dependent.",
            "Analytic class-prior correction is not guaranteed probability calibration.",
            "Co-holding correlations are lagged simple-return pair-day averages, not portfolio weights, causal risk estimates or executable hedges.",
            "No threshold selection, model promotion, original archive replacement, or protocol change."]}
    import sklearn,pyarrow
    report["runtime"]={"python":sys.version.split()[0],"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__,"pyarrow":pyarrow.__version__}
    output=Path(a.out)
    # Local explicit output only, never overwrite an existing report.
    blob=(json.dumps(report,indent=2,allow_nan=False)+"\n").encode()
    with output.open("xb") as f:f.write(blob)
    print("TEMPORAL_CALIBRATION_RESEARCH_ONLY",hashlib.sha256(blob).hexdigest(),len(folds),audits,flush=True)


if __name__=="__main__":
    main()
