from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from common import bh_fdr, ensure_dir, json_dump, load_config, write_table, zscore

def baseline_covariates(panel_path):
    d=pd.read_csv(panel_path,sep="\t",compression="infer",low_memory=False)
    d=d.sort_values(["person_id","visit_index"]).drop_duplicates("person_id")
    return d[["person_id","age","sex_male"]].rename(columns={"age":"baseline_age"})

def discover_outcomes(columns):
    out=[]
    for c in columns:
        if not c.endswith("_event"):
            continue
        stem=c[:-6]
        t=stem+"_time"
        if t in columns:
            out.append((stem,c,t))
    return out

def fit_cox(df,duration,event,exposure,covars):
    try:
        from lifelines import CoxPHFitter
    except Exception as exc:
        return {"status":f"lifelines_unavailable:{exc}"}
    use=[duration,event,exposure]+[c for c in covars if c in df.columns]
    x=df[use].copy()
    for c in use:
        x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.dropna()
    if len(x)<100 or x[event].sum()<20 or x[exposure].std(ddof=0)==0:
        return {"status":"insufficient_data","n":len(x),"events":int(x[event].sum()) if len(x) else 0}
    x[exposure]=zscore(x[exposure])
    model=CoxPHFitter(penalizer=0.001)
    model.fit(x,duration_col=duration,event_col=event,show_progress=False)
    row=model.summary.loc[exposure]
    return {
        "status":"ok","n":int(len(x)),"events":int(x[event].sum()),
        "coef_per_sd":float(row["coef"]),"hr_per_sd":float(np.exp(row["coef"])),
        "ci95_low":float(np.exp(row["coef lower 95%"])),
        "ci95_high":float(np.exp(row["coef upper 95%"])),
        "p":float(row["p"])
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--outcomes")
    ap.add_argument("--out-dir")
    a=ap.parse_args()
    cfg=load_config(a.config)
    root=Path(a.out_dir or cfg["paths"]["out_dir"])
    out=ensure_dir(root/"stage5_outcomes")
    outcome_path=Path(a.outcomes or cfg["paths"]["outcomes_file"])
    if not outcome_path.exists():
        info={"status":"not_run","reason":"outcomes_file_missing","path":str(outcome_path)}
        json_dump(info,out/"STAGE5_SUMMARY.json"); print(info); return 0

    base=pd.read_csv(root/"stage3_pace"/"SUBJECT_MULTI_ORGAN_PACE_SUMMARY.tsv.gz",
                     sep="\t",compression="infer",low_memory=False)
    disc_path=root/"stage4_discordance"/"SUBJECT_MULTI_ORGAN_DISCORDANCE_CLUSTER.tsv.gz"
    if disc_path.exists():
        disc=pd.read_csv(disc_path,sep="\t",compression="infer",low_memory=False)
        keep=["person_id","discordance_sd","discordance_range","cluster"]
        base=base.merge(disc[[c for c in keep if c in disc.columns]],on="person_id",how="left")
    cov=baseline_covariates(root/"stage1_longitudinal"/"LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz")
    base=base.merge(cov,on="person_id",how="left")
    y=pd.read_csv(outcome_path,sep="\t",compression="infer",low_memory=False)
    if "person_id" not in y.columns:
        raise SystemExit("Outcome file must contain person_id.")
    d=base.merge(y,on="person_id",how="inner")

    outcomes=discover_outcomes(d.columns)
    exposures=[c for c in ["multi_organ_pace_z","n_accelerated_organs",
                           "max_organ_pace_z","discordance_sd","discordance_range"] if c in d.columns]
    rows=[]
    for name,event,time in outcomes:
        for exposure in exposures:
            r=fit_cox(d,time,event,exposure,["baseline_age","sex_male"])
            r.update({"outcome":name,"event_col":event,"time_col":time,"exposure":exposure})
            rows.append(r)
    res=pd.DataFrame(rows)
    if not res.empty and "p" in res.columns:
        res["q_fdr"]=bh_fdr(res["p"])
    write_table(res,out/"OUTCOME_ASSOCIATIONS.tsv")
    info={"status":"ok","subjects_merged":int(len(d)),"outcomes":[x[0] for x in outcomes],
          "exposures":exposures,"models_tested":int(len(res)),
          "note":"Primary inference should pre-specify one outcome and one main exposure before controlled-data testing."}
    json_dump(info,out/"STAGE5_SUMMARY.json"); print(info); return 0

if __name__=="__main__":
    raise SystemExit(main())
