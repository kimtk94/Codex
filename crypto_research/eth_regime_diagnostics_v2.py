#!/usr/bin/env python3
"""Post-run diagnostic: check endpoint and redesign regime without changing original files."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,help="daily_regimes.csv from stage 1")
    p.add_argument("--out",required=True)
    a=p.parse_args()
    df=pd.read_csv(a.input,index_col=0,parse_dates=True)
    df.index=pd.to_datetime(df.index,utc=True)
    required=["close","log_return","vol30","trend_gap","dd90","ret7","observed"]
    missing=[x for x in required if x not in df.columns]
    if missing: raise ValueError(f"Missing columns: {missing}")
    df=df.sort_index()
    observed=df["observed"].astype(str).str.lower().eq("true")
    calibration=df.loc["2017":"2022"].copy()
    threshold=float(calibration["vol30"].dropna().quantile(.75))
    # orthogonal dimensions: trend vs volatility; stress is a separate risk flag
    gap=df["trend_gap"]
    trend=np.select([gap>=.025,gap<=-.025],["BULL","BEAR"],default="RANGE")
    vol=np.where(df["vol30"]>=threshold,"HIGH","LOW")
    df["regime_v2"]=np.char.add(np.char.add(trend.astype(str),"_"),vol.astype(str))
    # Distinguish acute shock (new large 7-day loss) from prolonged underwater drawdown
    df["acute_stress"]=(df["ret7"]<=-.18) & (df["vol30"]>=threshold)
    df["underwater_25pct"]=df["dd90"]<=-.25
    ready=observed.rolling(200,min_periods=200).sum().eq(200)
    df.loc[~ready,"regime_v2"]="WARMUP_OR_GAP"
    df["year"]=df.index.year
    eligible=df[df["regime_v2"]!="WARMUP_OR_GAP"]
    summary=eligible.groupby(["year","regime_v2"]).agg(
        days=("close","size"),median_vol=("vol30","median"),
        fwd7_mean=("forward_7d","mean"),
        fwd30_mean=("forward_30d","mean"),
        acute_stress_days=("acute_stress","sum"),
        underwater_days=("underwater_25pct","sum")
    ).reset_index()
    # Do not call mean returns predictive without accounting for overlapping windows.
    # Endpoint audit: 2023 Q4 may not exist even if all between-start/end dates exist.
    end=pd.Timestamp("2023-12-31",tz="UTC")
    last=df.index[observed].max()
    outcome={
        "first_observation":str(df.index[observed].min()),
        "last_observation":str(last),
        "days_missing_after_last_to_2023_12_31":max(0,(end-last).days),
        "calibration_2017_2022":int(((df.index.year<=2022)&ready).sum()),
        "holdout_2023":int(((df.index.year==2023)&ready).sum()),
        "high_vol_threshold":threshold,
        "note":"Spot/futures provenance not verified; no trade simulation. 2023 Q4 completeness must be checked."
    }
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    df.to_csv(dest/"daily_regimes_v2.csv")
    summary.to_csv(dest/"year_regime_summary_v2.csv",index=False)
    pd.Series(outcome).to_json(dest/"endpoint_audit_v2.json",force_ascii=False,indent=2)
    print(pd.Series(outcome).to_string())
    print(summary[summary.year==2023].to_string(index=False))
if __name__=="__main__":
    main()
