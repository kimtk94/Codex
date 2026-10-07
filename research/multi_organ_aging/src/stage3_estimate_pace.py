from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, LinearRegression
from common import ensure_dir, json_dump, load_config, write_table, zscore

def fit_slope(g, min_visits, min_followup):
    d = g[["year_offset","age_acceleration_z"]].dropna().sort_values("year_offset")
    if len(d) < min_visits:
        return None
    span = float(d.year_offset.max() - d.year_offset.min())
    if span < min_followup:
        return None
    x = (d.year_offset - d.year_offset.min()).to_numpy(float).reshape(-1,1)
    y = d.age_acceleration_z.to_numpy(float)
    ols = LinearRegression().fit(x,y)
    try:
        hub = HuberRegressor(alpha=0.0, max_iter=500).fit(x,y)
        slope = float(hub.coef_[0])
    except Exception:
        slope = float(ols.coef_[0])
    pred = ols.predict(x)
    den = float(np.sum((y-y.mean())**2))
    r2 = 1-float(np.sum((y-pred)**2))/den if den>0 else np.nan
    return {
        "n_visits":len(d),"followup_years":span,
        "baseline_accel_z":float(y[0]),"last_accel_z":float(y[-1]),
        "delta_accel_z":float(y[-1]-y[0]),
        "ols_slope_z_per_year":float(ols.coef_[0]),
        "huber_slope_z_per_year":slope,"ols_r2":r2
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--scores")
    ap.add_argument("--out-dir")
    a=ap.parse_args()
    cfg=load_config(a.config)
    root=Path(a.out_dir or cfg["paths"]["out_dir"])
    src=Path(a.scores or root/"stage2_clocks"/"ORGAN_AGE_SCORES_LONG.tsv.gz")
    out=ensure_dir(root/"stage3_pace")
    s=pd.read_csv(src,sep="\t",compression="infer",low_memory=False)
    rows=[]
    for (pid,organ),g in s.groupby(["person_id","organ"],sort=False):
        x=fit_slope(g,int(cfg["pace"]["min_visits"]),float(cfg["pace"]["min_followup_years"]))
        if x is not None:
            x.update({"person_id":pid,"organ":organ}); rows.append(x)
    if not rows:
        raise SystemExit("No subject-organ pair met pace requirements.")
    p=pd.DataFrame(rows)
    p["pace_z_within_organ"]=np.nan
    for organ,idx in p.groupby("organ").groups.items():
        p.loc[idx,"pace_z_within_organ"]=zscore(p.loc[idx,"huber_slope_z_per_year"]).to_numpy()
    th=float(cfg["pace"]["accelerated_threshold_sd"])
    p["accelerated_organ"]=(p.pace_z_within_organ>=th).astype(int)
    p["decelerated_organ"]=(p.pace_z_within_organ<=-th).astype(int)
    sm=(p.groupby("person_id").agg(
        n_organs=("organ","nunique"),
        mean_organ_pace_z=("pace_z_within_organ","mean"),
        max_organ_pace_z=("pace_z_within_organ","max"),
        min_organ_pace_z=("pace_z_within_organ","min"),
        n_accelerated_organs=("accelerated_organ","sum"),
        n_decelerated_organs=("decelerated_organ","sum"),
        median_followup_years=("followup_years","median")).reset_index())
    sm["multi_organ_pace_z"]=zscore(sm.mean_organ_pace_z)
    dom=(p.sort_values(["person_id","pace_z_within_organ"],ascending=[True,False])
        .drop_duplicates("person_id")[["person_id","organ","pace_z_within_organ"]]
        .rename(columns={"organ":"fastest_aging_organ","pace_z_within_organ":"fastest_aging_organ_pace_z"}))
    sm=sm.merge(dom,on="person_id",how="left")
    write_table(p,out/"SUBJECT_ORGAN_AGING_PACE.tsv.gz")
    write_table(sm,out/"SUBJECT_MULTI_ORGAN_PACE_SUMMARY.tsv.gz")
    info={"subject_organ_rows":len(p),"subjects":p.person_id.nunique(),
          "organs":sorted(p.organ.unique().tolist()),
          "subjects_with_3plus_organs":int((sm.n_organs>=3).sum())}
    json_dump(info,out/"STAGE3_SUMMARY.json")
    print(info)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
