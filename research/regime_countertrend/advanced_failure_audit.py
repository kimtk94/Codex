"""Exploratory daily-signal failure characterization. No LIVE changes."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

FEATURES=["rsi_delta3","macd_hist_delta3","adx14","adx_delta3","atr_pct","bb_pct_b","volume_ratio","qqq_rv20"]

def indicators(prices):
    p=prices.sort_values("date_ny").reset_index(drop=True).copy()
    p["date_ny"]=pd.to_datetime(p.date_ny)
    q=p.close_qqq.astype(float)
    fast=q.ewm(span=12,adjust=False,min_periods=12).mean()
    slow=q.ewm(span=26,adjust=False,min_periods=26).mean()
    macd=fast-slow
    hist=(macd-macd.ewm(span=9,adjust=False,min_periods=9).mean())/q
    p["macd_hist_delta3"]=hist-hist.shift(3)
    change=q.diff()
    gain=change.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-change).clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+gain/loss.replace(0,np.nan))
    p["rsi_delta3"]=rsi-rsi.shift(3)
    high=p.high_qqq.astype(float)
    low=p.low_qqq.astype(float)
    tr=pd.concat([high-low,(high-q.shift(1)).abs(),(low-q.shift(1)).abs()],axis=1).max(axis=1)
    up=high.diff()
    down=-low.diff()
    plus=up.where((up>down)&(up>0),0.)
    minus=down.where((down>up)&(down>0),0.)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    plus_di=100*plus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr
    minus_di=100*minus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr
    dx=100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0,np.nan)
    p["adx14"]=dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    p["adx_delta3"]=p.adx14-p.adx14.shift(3)
    qld=p.close_qld.astype(float)
    qld_tr=pd.concat([p.high_qld-p.low_qld,(p.high_qld-qld.shift(1)).abs(),(p.low_qld-qld.shift(1)).abs()],axis=1).max(axis=1)
    p["atr_pct"]=qld_tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/qld
    ma=q.rolling(20).mean();std=q.rolling(20).std()
    p["bb_pct_b"]=(q-(ma-2*std))/(4*std.replace(0,np.nan))
    p["volume_ratio"]=p.volume_qld/p.volume_qld.shift(1).rolling(20).median()
    p["qqq_rv20"]=q.pct_change().rolling(20).std()*np.sqrt(252)
    return p[["date_ny"]+FEATURES]

def audit(prices,trades):
    p=indicators(prices)
    t=trades.copy()
    t["date"]=pd.to_datetime(t.date)
    if t.date.duplicated().any():raise ValueError("duplicate trade signal date")
    t=t.merge(p,left_on="date",right_on="date_ny",validate="one_to_one",how="left")
    if t[FEATURES].isna().any().any():raise ValueError("missing signal-day indicators")
    dev=t[t.year<=2024]
    hold=t[t.year.between(2025,2026)]
    rows=[]
    for feature in FEATURES:
        loss=dev.loc[dev.failed,feature]
        success=dev.loc[~dev.failed,feature]
        a=hold.loc[hold.failed,feature]
        b=hold.loc[~hold.failed,feature]
        rows.append(dict(feature=feature,development_failure_n=len(loss),development_success_n=len(success),
            development_median_delta=float(loss.median()-success.median()),
            mann_whitney_p=float(mannwhitneyu(loss,success,alternative="two-sided").pvalue),
            holdout_failure_n=len(a),holdout_success_n=len(b),holdout_median_delta=float(a.median()-b.median())))
    summary=pd.DataFrame(rows)
    # Benjamini-Hochberg adjustment over the eight prespecified features.
    order=summary.mann_whitney_p.argsort().to_numpy()
    raw=summary.mann_whitney_p.to_numpy()
    qvals=np.empty(len(raw));minval=1.
    for i in range(len(raw)-1,-1,-1):
        index=order[i]
        minval=min(minval,raw[index]*len(raw)/(i+1))
        qvals[index]=minval
    summary["bh_fdr_q"]=qvals
    rules={"BASELINE":pd.Series(True,index=t.index),
      "RSI_RECOVERY":t.rsi_delta3>0,
      "MACD_IMPROVING":t.macd_hist_delta3>0,
      "RSI_MACD_RECOVERY":(t.rsi_delta3>0)&(t.macd_hist_delta3>0),
      "LOW_ADX_RECOVERY":(t.adx14<25)&(t.rsi_delta3>0)&(t.macd_hist_delta3>0)}
    results=[]
    for era,g in [("DEVELOPMENT",dev),("HOLDOUT_2025_2026",hold)]:
        for event,z in [("ALL",g),("UP_DIP",g[g.event=="UP_DIP"]),("DOWN_RALLY",g[g.event=="DOWN_RALLY"])]:
            for name,mask in rules.items():
                x=z.loc[mask.reindex(z.index).fillna(False)]
                results.append(dict(era=era,event=event,rule=name,n=len(x),
                   mean_net=float(x.net_return.mean()) if len(x) else None,
                   failure_rate=float(x.failed.mean()) if len(x) else None))
    return t,summary,pd.DataFrame(results)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--prices",required=True)
    a.add_argument("--trades",required=True)
    a.add_argument("--out",default="results/regime_countertrend/advanced")
    v=a.parse_args()
    t,s,r=audit(pd.read_csv(v.prices),pd.read_csv(v.trades))
    out=Path(v.out);out.mkdir(parents=True,exist_ok=True)
    t.to_csv(out/"trade_features.csv",index=False)
    s.to_csv(out/"feature_differences.csv",index=False)
    r.to_csv(out/"predefined_rules.csv",index=False)
    print(s.to_string(index=False));print(r[r.event=="ALL"].to_string(index=False))
