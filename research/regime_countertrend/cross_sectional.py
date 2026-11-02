"""Point-in-time cross-sectional market/sector exception screen (research only).

Input long panel CSV: date,symbol,close,sector,volume (volume optional).
Price features use observations through signal close. Forward labels never enter signal.
Output is NOT an execution backtest; sector classifications must be point-in-time.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

def screen(panel, market="QQQ", lookback=60, shock_days=5, fwd=5):
    required={"date","symbol","close","sector"}
    absent=required-set(panel.columns)
    if absent: raise ValueError(f"Missing columns: {sorted(absent)}")
    p=panel.copy()
    p["date"]=pd.to_datetime(p.date,errors="raise")
    if p.duplicated(["date","symbol"]).any(): raise ValueError("duplicate symbol/date")
    if p["close"].isna().any() or (p["close"]<=0).any(): raise ValueError("invalid prices")
    p=p.sort_values(["symbol","date"]).reset_index(drop=True)
    grp=p.groupby("symbol",sort=False)
    p["ret60"]=grp.close.pct_change(lookback)
    p["ret5"]=grp.close.pct_change(shock_days)
    p["fwd5"]=grp.close.shift(-fwd)/p.close-1
    m=p[p.symbol==market][["date","ret60","ret5","fwd5"]].rename(columns={"ret60":"market60","ret5":"market5","fwd5":"market_fwd5"})
    if m.empty: raise ValueError("market benchmark missing")
    p=p.merge(m,on="date",how="left",validate="many_to_one")
    p["market_regime"]=np.select([p.market60>=.08,p.market60<=-.08],["UP","DOWN"],default="SIDE")
    p.loc[p.market60.isna(),"market_regime"]="UNKNOWN"
    p["relative_ret5"]=p.ret5-p.market5
    sector=p[p.symbol!=market].groupby(["date","sector"],as_index=False).ret5.median().rename(columns={"ret5":"sector_median5"})
    p=p.merge(sector,on=["date","sector"],how="left",validate="many_to_one")
    p["sector_residual5"]=p.ret5-p.sector_median5
    p["type"]=np.select([
        (p.market_regime=="UP")&(p.relative_ret5<=-.03)&(p.sector_residual5<=-.02),
        (p.market_regime=="DOWN")&(p.relative_ret5>=.03)&(p.sector_residual5>=.02)
    ],["UP_IDIOSYNCRATIC_WEAK","DOWN_IDIOSYNCRATIC_STRONG"],default="NONE")
    p.loc[p.symbol==market,"type"]="NONE"
    events=p[(p.type!="NONE")&p.fwd5.notna()].copy()
    events["excess_fwd5"]=events.fwd5-events.market_fwd5
    return events,{"symbols":int(p.symbol.nunique()),"observations":len(p),"events":len(events),"type_counts":events.type.value_counts().to_dict(),"limitations":"Exploratory only. Sector median uses same-day peers and is not a tradable sector benchmark. Forward excess is unadjusted for beta, execution costs, overlapping events, and survivorship."}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--panel",required=True)
    a.add_argument("--out",default="results/cross_sectional")
    args=a.parse_args()
    e,m=screen(pd.read_csv(args.panel))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    e.to_csv(out/"events.csv",index=False)
    (out/"summary.json").write_text(json.dumps(m,ensure_ascii=False,indent=2))
    print(json.dumps(m,ensure_ascii=False))
if __name__=="__main__":main()
