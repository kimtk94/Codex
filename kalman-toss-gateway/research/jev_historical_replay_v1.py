from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ENGINE_ROOT = Path("/home/taehoon/.local/share/kalman-jev-shadow")
sys.path.insert(0, str(ENGINE_ROOT))
from engine.jev_shadow_decision_v1 import call_gateway, load_gateway_key, normalize_evaluation  # noqa: E402

DATA_ROOT = Path("/home/taehoon/.local/share/kalman-jev-backtest/data")
OUT_ROOT = Path("/home/taehoon/.local/share/kalman-jev-backtest/results")
OUT_ROOT.mkdir(parents=True, exist_ok=True)

MODEL = "typesafe-ai/jev"
COST_BPS = 10.0
HORIZON_BARS = 4

FROZEN_FEATURES = [
    "cs_ret_1b","cs_ret_2b","cs_ret_4b","cs_ret_6b",
    "cs_rv_6","cs_rv_24","cs_ma_dist_6","cs_ma_dist_24",
    "cs_volume_z_24","cs_bar_range","cs_beta24","cs_residual_ret_6b",
    "qqq_ret_2b","qqq_ret_6b","qqq_rv_24","qqq_ma_dist_24",
    "ix_trend_qqq","ix_vol_qqq","ix_ret1_qqq","ix_mom6_qqq",
]

SAFE_FEATURES = [
    *FROZEN_FEATURES,
    "ret_1b","ret_2b","ret_4b","ret_6b",
    "rv_6","rv_24","ma_dist_6","ma_dist_24","volume_z_24",
    "qqq_ret_1b","qqq_ret_4b",
    "beta24","residual_ret_6b",
]
SAFE_FEATURES = list(dict.fromkeys(SAFE_FEATURES))

UNIVERSE_FEATURES = [
    *FROZEN_FEATURES,
    "universe_mean_ret","universe_median_ret","universe_median_rv24",
    "relative_ret_4b",
]
UNIVERSE_FEATURES = list(dict.fromkeys(UNIVERSE_FEATURES))

MARKET_FEATURES = [
    *SAFE_FEATURES,
    "universe_mean_ret","universe_median_ret","universe_median_rv24",
    "relative_ret_4b",
]
MARKET_FEATURES = list(dict.fromkeys(MARKET_FEATURES))


def safe_float(v: Any) -> float | None:
    try:
        x=float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def load_panel() -> pd.DataFrame:
    panel=pd.read_parquet(DATA_ROOT/"r5_topk_common_trade_panel.parquet")
    detail=pd.read_parquet(DATA_ROOT/"r5_topk_portfolio_trade_detail.parquet")
    top=detail.loc[detail["portfolio"].eq("TOP1"),[
        "expected_seq","net_return","gross_return","cost_bps"
    ]].copy()
    scored=pd.read_parquet(DATA_ROOT/"r5_0_1_scored_rows.parquet")
    cols=["expected_seq","symbol","session_bucket","R5C0_HGB_REFERENCE"]+MARKET_FEATURES
    scored=scored[cols].copy()
    df=panel.merge(
        top,on="expected_seq",how="left",validate="one_to_one"
    ).merge(
        scored,
        left_on=["expected_seq","rank1_symbol"],
        right_on=["expected_seq","symbol"],
        how="left",
        validate="one_to_one",
    )
    if len(df)!=1340 or df["net_return"].isna().any() or df["symbol"].isna().any():
        raise RuntimeError("Historical panel join failed")
    if not np.allclose(df["rank1_score"],df["R5C0_HGB_REFERENCE"],equal_nan=False):
        raise RuntimeError("R5.1 score mismatch")
    return df.sort_values("expected_seq").reset_index(drop=True)


def state_for(row: pd.Series, variant: str, semantics_mode: str) -> dict[str,Any]:
    score=float(row["rank1_score"])
    top2=float(row["rank2_score"])
    top3=float(row["rank3_score"])
    top4=float(row["rank4_score"])
    signal={
        "r5_rank":1,
        "r5_score":score,
        "r5_score_bps":score*10000.0,
        "top1_score":score,
        "top2_score":top2,
        "top3_score":top3,
        "top4_score":top4,
        "top1_top2_gap":score-top2,
        "top1_top2_gap_bps":(score-top2)*10000.0,
        "top1_top3_gap":score-top3,
        "top1_top3_gap_bps":(score-top3)*10000.0,
        "score_semantics":"PREDICTED_RELATIVE_RET_4B_NOT_ABSOLUTE_RETURN",
        "friday_flat_applied":bool(row["friday_flat_applied"]),
    }
    if variant in {"MARKET","SAFE","UNIVERSE","FROZEN"}:
        market={}
        if variant=="FROZEN":
            feature_names = FROZEN_FEATURES
        elif variant=="SAFE":
            feature_names = SAFE_FEATURES
        elif variant=="UNIVERSE":
            feature_names = UNIVERSE_FEATURES
        else:
            feature_names = MARKET_FEATURES
        for k in feature_names:
            v=safe_float(row.get(k))
            if v is not None:
                market[k]=v
        signal["market_observed_features"]=market
        sb=row.get("session_bucket")
        if pd.notna(sb):
            signal["session_bucket"]=str(sb)

    if semantics_mode=="V12":
        instruction=(
            "Use only supplied numeric state. Candidate identity and absolute date are hidden. "
            "Assess a long entry over the supplied holding horizon after ordinary trading costs."
        )
        cost_note=(
            "assumed_total_cost_bps is the round-trip trading cost. The model score is a predicted "
            "relative 4-bar return signal, not a probability."
        )
    elif semantics_mode=="V13":
        instruction=(
            "Use only supplied numeric state. Candidate identity and absolute date are hidden. "
            "The R5 score is a cross-sectional relative-return ranking signal, NOT an estimate of "
            "the stock's absolute gross return. Do not subtract trading cost directly from the R5 score. "
            "Use score magnitude/gaps only as ranking-strength evidence and use the observed market features "
            "to judge whether taking the Top1 long candidate is likely to have positive NET return."
        )
        cost_note=(
            "assumed_total_cost_bps applies to the eventual stock trade return. It must not be directly "
            "compared with or subtracted from r5_score_bps because r5_score_bps is relative alpha, not absolute return."
        )
    else:
        raise ValueError(semantics_mode)

    return {
        "contract":{
            "strategy":"R5.1_BASE_HGB",
            "decision_role":"historical_blind_replay",
            "candidate_identity_blinded":True,
            "absolute_time_blinded":True,
            "future_outcome_hidden":True,
            "holding_horizon_bars":HORIZON_BARS,
            "assumed_total_cost_bps":COST_BPS,
            "input_variant":variant,
            "score_semantics_mode":semantics_mode,
            "instruction":instruction,
            "cost_interpretation":cost_note,
        },
        "signal":signal,
    }


def replay_one(rec: dict[str,Any], api_key: str, variant: str, semantics_mode: str) -> dict[str,Any]:
    row=pd.Series(rec)
    state=state_for(row,variant,semantics_mode)
    err=None
    for attempt in range(4):
        try:
            raw=call_gateway(state=state,api_key=api_key,model=MODEL,timeout_seconds=30)
            norm=normalize_evaluation(raw)
            return {
                "expected_seq":int(row["expected_seq"]),
                "variant":variant,
                "semantics_mode":semantics_mode,
                "entry_support":norm.get("entry_support"),
                "veto_probability":safe_float((norm.get("entry_support_probabilities") or {}).get("VETO")),
                "neutral_probability":safe_float((norm.get("entry_support_probabilities") or {}).get("NEUTRAL")),
                "support_probability":safe_float((norm.get("entry_support_probabilities") or {}).get("SUPPORT")),
                "positive_ev_probability":norm.get("positive_ev_probability"),
                "regime":norm.get("regime"),
                "conviction_score":norm.get("conviction_score"),
                "addon_support_probability":norm.get("addon_support_probability"),
                "usage":norm.get("usage") or {},
                "error":None,
            }
        except Exception as e:
            err=str(e)
            if attempt<3:
                time.sleep(1.5*(2**attempt))
    return {
        "expected_seq":int(row["expected_seq"]),
        "variant":variant,
        "semantics_mode":semantics_mode,
        "error":err,
    }


def read_checkpoint(path: Path) -> dict[int,dict[str,Any]]:
    out={}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        x=json.loads(line)
        out[int(x["expected_seq"])]=x
    return out


def run_replay(df: pd.DataFrame, variant: str, semantics_mode: str, workers: int) -> pd.DataFrame:
    tag=f"{semantics_mode.lower()}_{variant.lower()}"
    path=OUT_ROOT/f"jev_replay_{tag}.jsonl"
    done=read_checkpoint(path)
    todo=df.loc[~df["expected_seq"].isin(done)].copy()
    api_key=load_gateway_key({"gateway_key_file":"/home/taehoon/.config/kalman/secure/jev_gateway_key_create.out"})
    print(f"[{tag}] total={len(df)} checkpoint={len(done)} todo={len(todo)} workers={workers}",flush=True)

    if len(todo):
        records=todo.to_dict("records")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs={ex.submit(replay_one,r,api_key,variant,semantics_mode):r["expected_seq"] for r in records}
            completed=0
            with path.open("a",encoding="utf-8") as fh:
                for fut in as_completed(futs):
                    res=fut.result()
                    fh.write(json.dumps(res,ensure_ascii=False,default=str)+"\n")
                    fh.flush()
                    done[int(res["expected_seq"])]=res
                    completed+=1
                    if completed%25==0 or completed==len(records):
                        errs=sum(1 for x in done.values() if x.get("error"))
                        print(f"[{tag}] completed={completed}/{len(records)} total_checkpoint={len(done)} errors={errs}",flush=True)
    out=pd.DataFrame(list(done.values()))
    return df.merge(out,on="expected_seq",how="left",validate="one_to_one")


def max_drawdown(returns: np.ndarray) -> float:
    wealth=np.cumprod(1.0+returns)
    peak=np.maximum.accumulate(np.r_[1.0,wealth])[:-1]
    dd=wealth/peak-1.0
    return float(-np.min(dd)) if len(dd) else 0.0


def metrics(name: str, returns: pd.Series, mask: pd.Series, years: float) -> dict[str,Any]:
    r=returns.fillna(0).to_numpy(float)
    executed=mask.fillna(False).to_numpy(bool)
    rx=r[executed]
    n=len(r); ne=int(executed.sum())
    wealth=float(np.prod(1+r))
    total=wealth-1.0
    mdd=max_drawdown(r)
    opp_per_year=n/years if years>0 else np.nan
    sd=float(np.std(r,ddof=1)) if n>1 else np.nan
    sharpe=float(np.mean(r)/sd*np.sqrt(opp_per_year)) if sd and sd>0 else np.nan
    wins=rx[rx>0]; losses=rx[rx<0]
    pf=float(wins.sum()/abs(losses.sum())) if len(losses) and abs(losses.sum())>0 else np.nan
    return {
        "arm":name,
        "opportunities":n,
        "executed":ne,
        "coverage":ne/n if n else np.nan,
        "total_compound_return":total,
        "mean_return_per_opportunity":float(np.mean(r)),
        "mean_return_per_executed":float(np.mean(rx)) if ne else np.nan,
        "win_rate_executed":float(np.mean(rx>0)) if ne else np.nan,
        "profit_factor":pf,
        "sharpe_annualized_opportunity":sharpe,
        "max_drawdown":mdd,
        "return_over_mdd":total/mdd if mdd>0 else np.nan,
    }


def summarize(df: pd.DataFrame, tag: str) -> None:
    start=pd.to_datetime(df["entry_timestamp"],utc=True).min()
    end=pd.to_datetime(df["entry_timestamp"],utc=True).max()
    years=(end-start).total_seconds()/(365.25*86400)
    base=df["net_return"].astype(float)
    valid=df["error"].isna()
    arms=[]
    arms.append(metrics("A_R5.1_BASELINE",base,pd.Series(True,index=df.index),years))
    arms.append(metrics("B_JEV_NOT_VETO",base.where(valid & df["entry_support"].ne("VETO"),0.0),valid & df["entry_support"].ne("VETO"),years))
    arms.append(metrics("C_JEV_SUPPORT_ONLY",base.where(valid & df["entry_support"].eq("SUPPORT"),0.0),valid & df["entry_support"].eq("SUPPORT"),years))
    for th in (0.50,0.60,0.70,0.80,0.90):
        take=valid & (pd.to_numeric(df["veto_probability"],errors="coerce").fillna(1.0)<th)
        arms.append(metrics(f"B_VETO_P_LT_{th:.2f}",base.where(take,0.0),take,years))
    summary=pd.DataFrame(arms)
    summary.to_csv(OUT_ROOT/f"summary_{tag}.csv",index=False)

    year_rows=[]
    years_col=pd.to_datetime(df["entry_timestamp"],utc=True).dt.year
    for yr,gidx in df.groupby(years_col).groups.items():
        g=df.loc[gidx].copy()
        for arm,take in [
            ("A_R5.1_BASELINE",pd.Series(True,index=g.index)),
            ("B_JEV_NOT_VETO",g["error"].isna() & g["entry_support"].ne("VETO")),
            ("C_JEV_SUPPORT_ONLY",g["error"].isna() & g["entry_support"].eq("SUPPORT")),
        ]:
            rr=g["net_return"].astype(float).where(take,0.0)
            m=metrics(arm,rr,take,1.0)
            m["year"]=int(yr)
            year_rows.append(m)
    pd.DataFrame(year_rows).to_csv(OUT_ROOT/f"yearly_{tag}.csv",index=False)

    y=(base>0).astype(float)
    p=pd.to_numeric(df["positive_ev_probability"],errors="coerce")
    ok=valid & p.notna()
    brier=float(np.mean((p[ok]-y[ok])**2)) if ok.any() else np.nan
    label_counts=df.loc[valid,"entry_support"].value_counts(dropna=False).to_dict()
    diagnostic={
        "tag":tag,
        "rows":len(df),
        "valid":int(valid.sum()),
        "errors":int((~valid).sum()),
        "date_min":str(start),
        "date_max":str(end),
        "label_counts":label_counts,
        "positive_ev_brier":brier,
        "mean_positive_ev_probability":float(p[ok].mean()) if ok.any() else None,
        "actual_positive_net_rate":float(y.mean()),
    }
    (OUT_ROOT/f"diagnostic_{tag}.json").write_text(json.dumps(diagnostic,indent=2,default=str))
    df.to_parquet(OUT_ROOT/f"detail_{tag}.parquet",index=False)
    print("\nSUMMARY",tag)
    print(summary.to_string(index=False))
    print("\nDIAGNOSTIC",json.dumps(diagnostic,indent=2),flush=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--variant",choices=["MINIMAL","MARKET","SAFE","UNIVERSE","FROZEN"],required=True)
    ap.add_argument("--semantics-mode",choices=["V12","V13"],required=True)
    ap.add_argument("--workers",type=int,default=4)
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--even-sample",action="store_true")
    args=ap.parse_args()

    df=load_panel()
    if args.limit and args.limit<len(df):
        if args.even_sample:
            idx=np.linspace(0,len(df)-1,args.limit,dtype=int)
            df=df.iloc[idx].copy()
        else:
            df=df.iloc[:args.limit].copy()
    merged=run_replay(df,args.variant,args.semantics_mode,args.workers)
    summarize(merged,f"{args.semantics_mode.lower()}_{args.variant.lower()}")


if __name__=="__main__":
    main()
