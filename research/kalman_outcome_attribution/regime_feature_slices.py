"""Descriptive momentum/realized volatility slices on frozen candidate ledger."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from outcome_profile import load_archive, ARCHIVES, ASOF, KEY, normalize_keys
from risk_pilot import read
from sklearn.metrics import roc_auc_score

COLS=("rsi_proxy","macd_proxy","vol20","ret5","credit","tlt")

def market_context(prices):
    spy=prices["SPY"]
    mom=spy.pct_change(20,fill_method=None).shift(1)
    vol=spy.pct_change(fill_method=None).rolling(20).std().shift(1)*np.sqrt(252)
    x=pd.DataFrame({"momentum":np.select([mom>.02,mom<-.02],["UP","DOWN"],default="SIDEWAYS"),
        "volatility":np.where(vol>=.2,"HIGH","LOW"),
        "credit":(prices["HYG"]/prices["LQD"]).pct_change(5,fill_method=None).shift(1),
        "tlt":prices["TLT"].pct_change(5,fill_method=None).shift(1)},index=spy.index)
    return x.loc[mom.notna()&vol.notna()]

def close_features(c):
    d=c.diff();up=d.clip(lower=0);dn=-d.clip(upper=0)
    rsi=100-100/(1+up.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/
                    dn.ewm(alpha=1/14,adjust=False,min_periods=14).mean())
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    return pd.DataFrame({"rsi_proxy":rsi,"macd_proxy":(macd-macd.ewm(span=9,adjust=False).mean())/c,
        "vol20":c.pct_change(fill_method=None).rolling(20).std(),
        "ret5":c.pct_change(5,fill_method=None)},index=c.index)

def describe(g):
    r=g.net_return; y=r.le(-.05); n=len(r); dates=g.signal_date.nunique()
    return {"n":n,"dates":int(dates),"mean_net":float(r.mean()),
        "win_rate":float(r.gt(0).mean()),"severe":int(y.sum()),"severe_rate":float(y.mean()),
        "sparse_evidence":bool(dates<30 or y.sum()<20 or (~y).sum()<20),
        "severe_auc_descriptive":{k:float(roc_auc_score(y,g[k])) if y.nunique()==2 else None for k in COLS}}

def run(payload):
    prices={}
    for name in payload:
        if name.startswith("research/factor_lineage/") and name.endswith(".csv.gz") and "_repaired" not in name:
            d=read(payload,name)
            c=d.set_index(pd.to_datetime(d.session,errors="raise")).daily20_adjusted_close.astype(float).sort_index()
            if not c.index.is_unique or not np.isfinite(c).all() or not c.gt(0).all():
                raise ValueError("INVALID_CLOSE_SERIES")
            prices[Path(name).name.split(".")[0].upper()]=c
    a=read(payload,"research/oos_trades.csv")
    a["family"]=a.strategy.map({"LOGISTIC":"BULL_ML","TREND_RULE":"BULL_TREND"})
    b=read(payload,"research/regime_challenger/bear_oos_trades.csv")
    b["family"]=b.candidate_family.map({"BEAR_LOGISTIC":"BEAR_ML","BEAR_RULE":"BEAR_RULE"})
    e=normalize_keys(pd.concat([a,b],ignore_index=True))
    if e.family.value_counts().to_dict()!={"BULL_ML":439,"BULL_TREND":1061,"BEAR_ML":89,"BEAR_RULE":152} or e.duplicated(["family",*KEY]).any():
        raise ValueError("CANDIDATE_COVERAGE")
    if not np.allclose(e.gross_return-.002,e.net_return,rtol=0,atol=2e-9):
        raise ValueError("LABEL_MISMATCH")
    ctx=market_context(prices);rows=[]
    for s,g in e.groupby("symbol"):
        f=close_features(prices[s]).join(ctx)
        rows.append(g.merge(f,left_on="signal_date",right_index=True,validate="many_to_one"))
    x=pd.concat(rows,ignore_index=True)
    if len(x)!=1741 or not np.isfinite(x[list(COLS)]).all().all() or x[["momentum","volatility"]].isna().any().any():
        raise ValueError("FEATURE_COVERAGE")
    groups={}
    for keys in (["momentum","volatility"],["family","momentum"],["family","volatility"],["family","momentum","volatility"]):
        groups["+".join(keys)]=[{**dict(zip(keys,k)),**describe(g)} for k,g in x.groupby(keys)]
    return {"schema":"kalman-regime-feature-slices-v1","research_only":True,
        "production_writes":False,"approved_live":False,"new_holdout":False,
        "source_sha256":ARCHIVES["results"][2],"asof":ASOF,"candidate_count":len(x),
        "thresholds":{"momentum_abs":.02,"annualized_realized_vol":.2,"lag_sessions":1},
        "groups":groups,"limitations":["Inspected retrospective selected candidates; overlapping dates.",
        "Pooled strata confound strategy and symbol composition. No causal inference or threshold selection.",
        "RSI and MACD are close-derived proxies, not exact TA-Lib; no ATR or portfolio replay.",
        "Sparse flags are descriptive minimums, not a statistical power guarantee."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();r=run(load_archive(a.results,"results"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n")
    print("REGIME_FEATURE_SLICES_RESEARCH_ONLY",r["candidate_count"])

if __name__=="__main__":main()
