"""All-daily historical feasibility of #1078, independent of nonoverlap selection.

Uses the exact pinned original model implementations and original archived
market/TA data. Overlapping outcomes are diagnostic shadow observations.
No new first-seal evidence, parameter change, trade or journal write.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, KEY, load_archive, load_original, csv
from protocol_feasibility import HIGH_RISK, compare, bear_episodes, rolling_feasibility, paired_date_diagnostic
from daily_gate_risk import analyze as gate_risk
from daily_tail_attribution import analyze as tail_attribution
from sector_tail_excess import analyze as sector_tail_excess

CORE="SPY QQQ QLD IWM AAPL MSFT AMZN GOOGL META NVDA AMD AVGO MU TSLA PLTR IONQ COIN MSTR JPM XOM".split()


def daily_candidates(test,family,threshold=.60):
    if family=="BULL":
        gate=test.spy_above200_lag.ge(.5)&test.vix_lag.le(35)
        cols=["ret5","spy_mom5_lag"]
    elif family=="BEAR":
        gate=test.spy_above200_lag.lt(.5)&test.vix_lag.gt(0)&test.vix_lag.le(45)
        cols=["vix_lag","gld_mom5_lag"]
    else:
        raise ValueError("UNKNOWN_MODEL_FAMILY")
    q=test.loc[gate&test.prob.ge(threshold)&test.net_return.notna()].copy()
    if not np.isfinite(q[cols]).all().all():
        raise ValueError("MISSING_DISCOVERY_GATE_INPUT")
    q["qualifies"]=(q.ret5.lt(0)&q.spy_mom5_lag.ge(0) if family=="BULL"
                    else q.vix_lag.ge(20)&q.gld_mom5_lag.ge(0))
    return q


def archive_replay(frame,original,train):
    rows=[]
    for s,g in frame.groupby("symbol"):
        for t in train.nonoverlap(g,"LOGISTIC"):
            rows.append({"symbol":s,**t})
    replay=pd.DataFrame(rows)
    j=replay.merge(original,on=KEY,how="outer",validate="one_to_one",indicator=True)
    if not j._merge.eq("both").all():
        raise ValueError("ARCHIVED_NONOVERLAP_KEYS_MISMATCH")
    score=float((j.probability_x-j.probability_y).abs().max())
    label=float((j.net_return_x-j.net_return_y).abs().max())
    if not np.isfinite([score,label]).all() or score>2e-6 or label>1e-10:
        raise ValueError("ARCHIVED_MODEL_OR_RETURN_MISMATCH")
    return {"original":len(original),"replayed":len(replay),"score_max_abs_error":score,
            "return_max_abs_error":label}


def date_strings(frame):
    q=frame.copy()
    q["signal_date"]=q.index.strftime("%Y-%m-%d")
    for k in ("entry_date","exit_date"):
        q[k]=q[k].dt.strftime("%Y-%m-%d")
    return q.reset_index(drop=True)


def report(raw,result,train):
    from regime_challenger import fit_bear_year
    ctx=csv(result,"research/regime_challenger/regime_session_context.csv").set_index("date")
    if len(ctx)!=727 or not ctx.index.is_unique or not ctx.index.is_monotonic_increasing:
        raise ValueError("FROZEN_SESSION_CALENDAR_MISMATCH")
    full={k:[] for k in ("BULL","BEAR")};folds=0;coverage=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name,blob in raw.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
        market=root/"market";features=root/"features"
        context=train.context_frame(market)
        benchmark_prices={s:train.load_bars(train.market_file(market,s))[["open","close"]]
                          for s in ("SPY","QQQ","SMH")}
        for s in CORE:
            f=train.feature_frame(s,market,features,context,20.)
            for y in (2024,2025,2026):
                for family,fn in (("BULL",train.model_year),("BEAR",fit_bear_year)):
                    estimator,test,details=fn(f,y)
                    if estimator is None or test is None:
                        raise ValueError("UNEXPECTED_FROZEN_MODEL_ABSTENTION")
                    q=daily_candidates(test,family)
                    q["symbol"]=s
                    full[family].append(q)
                    coverage.append({"symbol":s,"year":y,"family":family,
                                     "completed_label_rows":len(test),"qualified":len(q)})
                    folds+=1
    panels={k:pd.concat(v) for k,v in full.items()}
    if folds!=120 or sum(c["completed_label_rows"] for c in coverage if c["family"]=="BULL")!=14460:
        raise ValueError("FROZEN_MODEL_COVERAGE_MISMATCH")
    old=csv(result,"research/regime_challenger/bear_model_coverage.csv")
    c=pd.DataFrame(coverage);c=c.loc[c.family.eq("BEAR")]
    j=c.merge(old,on=["symbol","year"],validate="one_to_one")
    if (len(j)!=60 or not j.qualified.eq(j.logistic_qualified_rows).all()
            or not j.completed_label_rows_x.eq(j.completed_label_rows_y).all()
            or not j.bear_model_fit.all()):
        raise ValueError("ARCHIVED_BEAR_DAILY_COVERAGE_MISMATCH")
    bull=csv(result,"research/oos_trades.csv")
    bear=csv(result,"research/regime_challenger/bear_oos_trades.csv")
    replay={"BULL":archive_replay(panels["BULL"],bull.loc[bull.strategy.eq("LOGISTIC")],train),
            "BEAR":archive_replay(panels["BEAR"],bear.loc[bear.candidate_family.eq("BEAR_LOGISTIC")],train)}
    a,b=(date_strings(panels[k]) for k in ("BULL","BEAR"))
    if len(a)!=1200 or len(b)!=267 or any(q.duplicated(["symbol","signal_date"]).any() for q in (a,b)):
        raise ValueError("FROZEN_ALL_DAILY_CANDIDATE_MISMATCH")
    ids,episodes=bear_episodes(ctx);b["episode"]=b.signal_date.map(ids)
    if not b.episode.isin(episodes).all():
        raise ValueError("BEAR_EPISODE_MAPPING_MISMATCH")
    # Remove the four unresolved final signal sessions, unlike the older
    # nonoverlap diagnostic which counted the entire 727-session calendar.
    cal=ctx.index[:-4]
    if len(cal)!=723 or not a.signal_date.isin(cal).all() or not b.signal_date.isin(cal).all():
        raise ValueError("COMPLETED_LABEL_CALENDAR_MISMATCH")
    out={}
    for name,excluded in (("PRIMARY16",HIGH_RISK),("ALL20",set())):
        x,y=a.loc[~a.symbol.isin(excluded)],b.loc[~b.symbol.isin(excluded)]
        ep=[{"start":s,"end":e,"sessions":n,**compare(y.loc[y.episode.eq(i)])}
            for i,(s,e,n) in episodes.items()]
        contrasts=[g["equal_date_group_difference"] for g in ep
                   if g["equal_date_group_difference"] is not None]
        out[name]={"bull":compare(x),"bear":compare(y),"bear_episodes":ep,
            "bear_equal_episode_difference":float(np.mean(contrasts)) if contrasts else None,
            "annual":{str(i):{"bull":compare(x.loc[x.signal_date.str[:4].eq(str(i))]),
                              "bear":compare(y.loc[y.signal_date.str[:4].eq(str(i))])} for i in (2024,2025,2026)},
            "bull_date_diagnostic":paired_date_diagnostic(x,cal),
            "daily_gate_risk":{"BULL":gate_risk(x,"BULL",cal),
                               "BEAR":gate_risk(y,"BEAR",cal)},
            "daily_tail_attribution":{"BULL":tail_attribution(x,"BULL"),
                                      "BEAR":tail_attribution(y,"BEAR")},
            "sector_tail_excess":{"BULL":sector_tail_excess(x,"BULL",benchmark_prices),
                                  "BEAR":sector_tail_excess(y,"BEAR",benchmark_prices)},
            "rolling_252_session_feasibility":rolling_feasibility(x,y,cal,episodes)}
    return {"schema":"kalman-all-daily-protocol-feasibility-v1",
        "input_sha256":{k:v[2] for k,v in ARCHIVES.items()},
        "protocol":"https://github.com/kimtk94/Codex/issues/1078",
        "research_only":True,"approved_live":False,"production_writes":False,
        "new_holdout":False,"primary_study_admitted_outcomes":0,"protocol_changed":False,
        "source_finality_certified":False,"model_folds":folds,
        "archived_bear_coverage_rows_reconciled":len(j),"original_candidate_replay":replay,
        "completed_label_sessions":len(cal),"cohorts":out,
        "limitations":["All-daily candidate observations overlap in their four-session outcomes; not executed trades.",
            "All models use previously inspected historical inputs and original fixed thresholds.",
            "Historical count feasibility is not a future probability or power guarantee.",
            "No independent source certification, original first-seal evidence or new study admission."]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("data","results","original-source","out"):
        p.add_argument("--"+k,required=True)
    a=p.parse_args()
    r=report(load_archive(a.data,"data"),load_archive(a.results,"results"),load_original(a.original_source))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n")
    print("ALL_DAILY_FEASIBILITY_RESEARCH_ONLY",r["model_folds"],r["completed_label_sessions"])
