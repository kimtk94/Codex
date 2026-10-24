#!/usr/bin/env python3
"""Read-only Triple Barrier event research. No live trading or broker access."""
import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np

def read(path, fields):
    df = pd.read_csv(path)
    missing = set(fields) - set(df)
    if missing: raise ValueError(f"{path}: missing {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df

def stats(df):
    if df.empty: return {"trades": 0}
    r = df.net_return.astype(float)
    equity = (1+r).cumprod()
    peak = np.maximum.accumulate(np.r_[1.0,equity.to_numpy()])[1:]
    return {"trades": len(df), "win_rate_pct": round(100*(r>0).mean(),4),
      "return_pct": round(100*(equity.iloc[-1]-1),4),
      "mdd_pct": round(100*min(0,(equity/peak-1).min()),4),
      "mean_return_pct": round(100*r.mean(),4)}

def simulate(signals,bars,mode,tp,sl,hold,fees,atr_window,reference):
    results=[]
    for symbol,g in bars.sort_values("date").groupby("symbol"):
        g=g.reset_index(drop=True).copy()
        previous=g.close.shift()
        tr=pd.concat([g.high-g.low,(g.high-previous).abs(),(g.low-previous).abs()],axis=1).max(axis=1)
        g["prior_atr"]=tr.rolling(atr_window,min_periods=atr_window).mean().shift(1)
        ix={v:i for i,v in enumerate(g.date)}
        for sig in signals[signals.symbol==symbol].itertuples(index=False):
            if sig.date not in ix: continue
            j=ix[sig.date]+1  # next day's open only, no same-bar information
            if j+hold>len(g): continue
            entry=float(g.iloc[j].open)
            if entry<=0: continue
            scale=1.
            if mode=="vol":
                a=float(g.iloc[j].prior_atr)
                prev=float(g.iloc[j-1].close)
                if not np.isfinite(a) or prev<=0: continue
                scale=float(np.clip(a/prev/reference,0.5,2.))
            ceiling=entry*(1+tp*scale)
            floor=entry*(1-sl*scale)
            reason="TIME"; exit_price=float(g.iloc[j+hold-1].close)
            exit_date=g.iloc[j+hold-1].date
            for k in range(j,j+hold):
                b=g.iloc[k]
                if b.open<=floor: exit_price=float(b.open); reason="SL_GAP"
                elif b.open>=ceiling: exit_price=float(b.open); reason="TP_GAP"
                elif b.low<=floor: exit_price=floor; reason="SL"
                elif b.high>=ceiling: exit_price=ceiling; reason="TP"
                else: continue
                exit_date=b.date
                break
            net=(exit_price/entry)*(1-fees/10000)**2-1
            results.append({"signal_id":str(sig.signal_id),"strategy":str(sig.strategy),
              "symbol":symbol,"regime":str(getattr(sig,"regime","UNKNOWN")),"mode":mode,
              "entry_date":g.iloc[j].date.strftime("%Y-%m-%d"),"exit_date":exit_date.strftime("%Y-%m-%d"),
              "entry":entry,"exit":exit_price,"exit_reason":reason,
              "barrier_tp":tp*scale,"barrier_sl":sl*scale,"net_return":net})
    return pd.DataFrame(results)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--signals",required=True); p.add_argument("--bars",required=True)
    p.add_argument("--baseline-trades"); p.add_argument("--out",default="outputs/triple_barrier")
    p.add_argument("--tp",type=float,default=.03); p.add_argument("--sl",type=float,default=.03)
    p.add_argument("--sessions",type=int,default=4); p.add_argument("--fee-bps",type=float,default=0)
    p.add_argument("--atr-window",type=int,default=14); p.add_argument("--vol-reference",type=float,default=.02)
    a=p.parse_args()
    if min(a.tp,a.sl,a.sessions,a.atr_window,a.vol_reference)<=0 or a.fee_bps<0: p.error("invalid parameters")
    signals=read(a.signals,["signal_id","strategy","symbol","date"])
    bars=read(a.bars,["symbol","date","open","high","low","close"])
    if signals.empty or bars.empty: raise ValueError("real signals and bars required; no synthetic data")
    if signals.signal_id.duplicated().any() or bars.duplicated(["symbol","date"]).any():
        raise ValueError("duplicate signal ID or bar")
    for c in ["open","high","low","close"]: bars[c]=pd.to_numeric(bars[c],errors="raise")
    if not np.isfinite(bars[["open","high","low","close"]].to_numpy()).all() or (bars[["open","high","low","close"]]<=0).any().any():
        raise ValueError("invalid price")
    if (bars.high<bars[["open","low","close"]].max(axis=1)).any() or (bars.low>bars[["open","high","close"]].min(axis=1)).any():
        raise ValueError("inconsistent OHLC")
    chunks=[simulate(signals,bars,m,a.tp,a.sl,a.sessions,a.fee_bps,a.atr_window,a.vol_reference) for m in ("fixed","vol")]
    result=pd.concat(chunks,ignore_index=True)
    if result.empty: raise ValueError("no historical signals with enough forward bars")
    result=result.sort_values(["strategy","mode","entry_date","signal_id"])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    result.to_csv(out/"trades.csv",index=False)
    report={}
    for (strategy,mode),df in result.groupby(["strategy","mode"]):
        row=stats(df)
        row["by_regime"]={str(k):stats(v) for k,v in df.groupby("regime")}
        row["exit_reasons"]=df.exit_reason.value_counts().to_dict()
        report.setdefault(strategy,{})[mode]=row
    if a.baseline_trades:
        base=pd.read_csv(a.baseline_trades)
        missing={"signal_id","strategy","net_return"}-set(base)
        if missing: raise ValueError(f"baseline missing: {missing}")
        if base.signal_id.duplicated().any(): raise ValueError("duplicate baseline signal_id")
        base["signal_id"]=base.signal_id.astype(str)
        for (strategy,mode),df in result.groupby(["strategy","mode"]):
            match=df.merge(base[["signal_id","strategy","net_return"]],on=["signal_id","strategy"],suffixes=("_tb","_base"))
            if len(match):
                report[strategy][mode]["matched_baseline"]={
                  "events":len(match),"baseline_mean_pct":round(100*match.net_return_base.mean(),4),
                  "incremental_mean_pp":round(100*(match.net_return_tb-match.net_return_base).mean(),4)}
    payload={"status":"COMPLETE","note":"EVENT STUDY: sequential-event compounded return/MDD are proxies, NOT executable portfolio metrics; overlapping exposure possible. Historical baseline required for incremental comparison.","params":{"tp":a.tp,"sl":a.sl,"sessions":a.sessions,"fee_bps_each_side":a.fee_bps,"atr_window":a.atr_window,"vol_reference":a.vol_reference},"results":report}
    (out/"summary.json").write_text(json.dumps(payload,indent=2),encoding="utf8")
    print(json.dumps(payload))

if __name__=="__main__": main()
