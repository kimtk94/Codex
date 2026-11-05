"""Gap-aware OHLC sensitivity and expanding walk-forward audit. Research only.

Not live fills; no portfolio equity curve, MDD, or authorization to change LIVE.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

RULES=("BASELINE","MA20_POS","MACD_POS","RSI_40_65","RSI_RISING","MACD_RISING","RSI_AND_MACD_RISING","MA20_AND_MACD")

def signal_features(prices):
    p=prices.sort_values("date_ny").reset_index(drop=True).copy()
    if p.date_ny.duplicated().any(): raise ValueError("duplicate price dates")
    q=p.close_qqq.astype(float)
    fast=q.ewm(span=12,adjust=False,min_periods=12).mean()
    slow=q.ewm(span=26,adjust=False,min_periods=26).mean()
    macd=fast-slow
    hist=(macd-macd.ewm(span=9,adjust=False,min_periods=9).mean())/q
    diff=q.diff()
    gain=diff.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-diff).clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+gain/loss.replace(0,np.nan))
    p["MA20_POS"]=q>=q.rolling(20,min_periods=20).mean()
    p["MACD_POS"]=hist>0
    p["RSI_40_65"]=rsi.between(40,65)
    p["RSI_RISING"]=rsi>rsi.shift(3)
    p["MACD_RISING"]=hist>hist.shift(3)
    p["RSI_AND_MACD_RISING"]=p.RSI_RISING&p.MACD_RISING
    p["MA20_AND_MACD"]=p.MA20_POS&p.MACD_POS
    return p[["date_ny"]+list(RULES[1:])]

def simulate(prices,signal_i,scenario="STOP_FIRST",roundtrip_bps=20,hold_days=4):
    if scenario not in ("STOP_FIRST","TARGET_FIRST"):raise ValueError("invalid scenario")
    if signal_i+hold_days>=len(prices):raise ValueError("insufficient forward bars")
    entry=float(prices.iloc[signal_i+1].open_qld)
    if not np.isfinite(entry) or entry<=0:raise ValueError("bad entry")
    sl,tp=entry*.97,entry*1.03
    exit_index=signal_i+hold_days
    exit_price=float(prices.iloc[exit_index].close_qld)
    outcome="TIME";ambiguous=False;gap=False
    for j in range(signal_i+1,signal_i+hold_days+1):
        row=prices.iloc[j]
        op,hi,lo=float(row.open_qld),float(row.high_qld),float(row.low_qld)
        if not all(map(np.isfinite,(op,hi,lo))) or not (0<lo<=op<=hi):
            raise ValueError("invalid OHLC")
        if j>signal_i+1 and op<=sl:
            outcome="GAP_SL";exit_price=op;exit_index=j;gap=True;break
        if j>signal_i+1 and op>=tp:
            outcome="GAP_TP";exit_price=op;exit_index=j;gap=True;break
        if lo<=sl and hi>=tp:
            ambiguous=True;exit_index=j
            outcome="AMBIGUOUS_STOP_FIRST" if scenario=="STOP_FIRST" else "AMBIGUOUS_TARGET_FIRST"
            exit_price=sl if scenario=="STOP_FIRST" else tp
            break
        if lo<=sl:
            outcome="SL";exit_price=sl;exit_index=j;break
        if hi>=tp:
            outcome="TP";exit_price=tp;exit_index=j;break
    return {"net":exit_price/entry-1-roundtrip_bps/10000,
       "gross":exit_price/entry-1,"outcome":outcome,
       "exit_date":prices.iloc[exit_index].date_ny,"ambiguity":ambiguous,
       "gap":gap,"entry":entry,"exit":exit_price}

def build_events(prices,raw_events):
    p=prices.sort_values("date_ny").reset_index(drop=True)
    e=raw_events.copy()
    if e.date.duplicated().any():raise ValueError("duplicate signal dates")
    idx=pd.Series(p.index,index=p.date_ny)
    if not e.date.isin(idx.index).all():raise ValueError("unknown signals")
    rows=[]
    for _,r in e.iterrows():
        i=int(idx.loc[r.date])
        worst=simulate(p,i,"STOP_FIRST")
        best=simulate(p,i,"TARGET_FIRST")
        rows.append({"date":r.date,"year":int(str(r.date)[:4]),"event":r.event,
          "exit_date":worst["exit_date"],"net_20bp":worst["net"],
          "net_40bp":worst["gross"]-.004,"net_80bp":worst["gross"]-.008,
          "bestcase_net_20bp":best["net"],"sl_first_outcome":worst["outcome"],
          "was_gap":worst["gap"],"was_ambiguous":worst["ambiguity"]})
    t=pd.DataFrame(rows)
    if len(t)!=len(e):raise ValueError("signal count changed")
    t=t.merge(signal_features(p),left_on="date",right_on="date_ny",validate="one_to_one",how="left")
    if t[list(RULES[1:])].isna().any().any():raise ValueError("missing signal features")
    t["BASELINE"]=True
    return t.sort_values("date").reset_index(drop=True)

def measure(g,mask,return_col):
    keep=g[mask]
    return {"opportunities":len(g),"taken":len(keep),
        "mean_net_taken":float(keep[return_col].mean()) if len(keep) else None,
        "mean_net_per_opportunity":float(keep[return_col].sum()/len(g)) if len(g) else None,
        "sum_trade_returns_not_portfolio":float(keep[return_col].sum()),
        "blocked_losers":int((g.loc[~mask,return_col]<0).sum()),
        "blocked_winners":int((g.loc[~mask,return_col]>=0).sum())}

def fixed_comparison(events,return_col="net_20bp"):
    rows=[]
    for era,g in (("DEVELOPMENT_PRE2025",events[events.year<=2024]),
                  ("REVISITED_2025_2026",events[events.year.between(2025,2026)])):
        for event,z in (("ALL",g),("UP_DIP",g[g.event=="UP_DIP"]),
                        ("DOWN_RALLY",g[g.event=="DOWN_RALLY"])):
            for rule in RULES:
                rows.append({"era":era,"event":event,"rule":rule,
                             **measure(z,z[rule].astype(bool),return_col)})
    return pd.DataFrame(rows)

def choose_rule(train,return_col="net_20bp"):
    # Prespecified eligibility: at least 20 earlier events / 3 training years,
    # >=8 kept, >=30% signal retention, >=10bp improvement per opportunity.
    if len(train)<20 or train.year.nunique()<3:return "BASELINE"
    baseline=measure(train,train.BASELINE.astype(bool),return_col)["mean_net_per_opportunity"]
    threshold=baseline+.001;winner="BASELINE"
    for rule in RULES[1:]:
        mask=train[rule].astype(bool)
        if int(mask.sum())<8 or float(mask.mean())<.30:continue
        value=measure(train,mask,return_col)["mean_net_per_opportunity"]
        if value>threshold+1e-12:
            threshold=value;winner=rule
    return winner

def annual_walkforward(events,first_year=2020,return_col="net_20bp"):
    folds=[]
    for year in sorted(int(y) for y in events.year.unique() if int(y)>=first_year):
        test=events[events.year==year]
        if test.empty:continue
        # Purge cross-year outcomes; use only completed prior exits.
        train=events[(events.year<year)&
             (pd.to_datetime(events.exit_date)<pd.Timestamp(f"{year}-01-01"))]
        chosen=choose_rule(train,return_col)
        for label,rule in (("BASELINE","BASELINE"),("WALK_FORWARD_SELECTED",chosen)):
            folds.append({"year":year,"label":label,"rule":rule,
                "training_n":len(train),
                "training_last_exit":str(train.exit_date.max()) if len(train) else None,
                **measure(test,test[rule].astype(bool),return_col)})
    return pd.DataFrame(folds)

def audit(prices,trades):
    t=build_events(prices,trades)
    fixed={k:fixed_comparison(t,col) for k,col in
          (("20bp","net_20bp"),("40bp","net_40bp"),("80bp","net_80bp"))}
    wf=annual_walkforward(t)
    w=wf[wf.label=="WALK_FORWARD_SELECTED"]
    b=wf[wf.label=="BASELINE"]
    n=int(b.opportunities.sum())
    x=float(w.sum_trade_returns_not_portfolio.sum())
    y=float(b.sum_trade_returns_not_portfolio.sum())
    verdict={"status":"HOLD_RESEARCH_ONLY","signal_count":len(t),
       "data_last_date":str(prices.date_ny.max()),
       "gap_exits":int(t.was_gap.sum()),
       "ambiguous_events":int(t.was_ambiguous.sum()),
       "wf_opportunities":n,"wf_taken":int(w.taken.sum()),
       "wf_baseline_mean_net_per_opportunity":y/n if n else None,
       "wf_selected_mean_net_per_opportunity":x/n if n else None,
       "wf_incremental_mean_per_opportunity":(x-y)/n if n else None,
       "wf_nonbaseline_years":int((w.rule!="BASELINE").sum()),
       "approval_allowed":False,
       "limitations":["Daily OHLC proxy; NOT actual first 15-minute-fill or broker record",
          "2025-26 is revisited, not untouched OOS",
          "Prior rule exploration and small year slices permit selection bias",
          "Overlapping trades; not iid; no capital-weighted MDD, CAGR, or equity curve",
          "Costs are flat scenarios, not verified real trading costs"]}
    return t,fixed,wf,verdict

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--prices",required=True)
    ap.add_argument("--trades",required=True)
    ap.add_argument("--out",default="results/regime_countertrend/robustness")
    args=ap.parse_args()
    events,fixed,wf,meta=audit(pd.read_csv(args.prices),pd.read_csv(args.trades))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    events.to_csv(out/"events.csv",index=False)
    wf.to_csv(out/"annual_walkforward.csv",index=False)
    for cost,tab in fixed.items():tab.to_csv(out/f"fixed_{cost}.csv",index=False)
    (out/"verdict.json").write_text(json.dumps(meta,indent=2))
    print("ROBUST_WF",json.dumps(meta))
    print(wf.to_string(index=False))
