"""Research-only MACD/RSI/MA20 regime filter comparison on QLD trade proxy."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

def audit(prices,trades):
    d=prices.sort_values("date_ny").copy()
    close=d.close_qqq
    fast=close.ewm(span=12,adjust=False,min_periods=12).mean()
    slow=close.ewm(span=26,adjust=False,min_periods=26).mean()
    line=fast-slow
    signal=line.ewm(span=9,adjust=False,min_periods=9).mean()
    delta=close.diff()
    gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-delta).clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d["macd_positive"]=(line-signal)>0
    d["rsi14"]=100-100/(1+gain/loss.replace(0,np.nan))
    d["ma_gate"]=close>=close.rolling(20).mean()
    d["date_ny"]=pd.to_datetime(d.date_ny)
    t=trades.copy()
    t["date"]=pd.to_datetime(t.date)
    t=t.merge(d[["date_ny","macd_positive","rsi14","ma_gate"]],left_on="date",right_on="date_ny",how="left",validate="one_to_one")
    if t.macd_positive.isna().any():raise ValueError("missing signal-day indicator")
    t["rsi_gate"]=t.rsi14.between(40,65)
    t["ma_macd"]=t.ma_gate&t.macd_positive
    t["two_of_three"]=(t.ma_gate.astype(int)+t.macd_positive.astype(int)+t.rsi_gate.astype(int))>=2
    rules={"BASELINE":pd.Series(True,index=t.index),"MA20":t.ma_gate,"MACD":t.macd_positive,"RSI_40_65":t.rsi_gate,"MA20_MACD":t.ma_macd,"TWO_OF_THREE":t.two_of_three}
    rows=[]
    for era,group in [("DEVELOPMENT",t[t.year<=2024]),("HOLDOUT_2025_2026",t[t.year.between(2025,2026)])]:
        for name,mask in rules.items():
            x=group[mask.loc[group.index]]
            rows.append({"era":era,"filter":name,"n":len(x),"mean_net_return":x.net_return.mean() if len(x) else np.nan,"loss_rate":x.failed.mean() if len(x) else np.nan})
    return t,pd.DataFrame(rows)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--prices",required=True)
    p.add_argument("--trades",required=True)
    p.add_argument("--out",default="results/regime_countertrend/multifactor")
    a=p.parse_args()
    t,s=audit(pd.read_csv(a.prices),pd.read_csv(a.trades))
    output=Path(a.out);output.mkdir(parents=True,exist_ok=True)
    t.to_csv(output/"trade_features.csv",index=False)
    s.to_csv(output/"rule_comparison.csv",index=False)
    print(s.to_string(index=False))
