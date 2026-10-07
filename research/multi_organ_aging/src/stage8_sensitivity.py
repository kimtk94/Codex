from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from common import ensure_dir, json_dump, load_config, write_table, zscore

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--out-dir")
    a=ap.parse_args()
    cfg=load_config(a.config)
    root=Path(a.out_dir or cfg["paths"]["out_dir"])
    out=ensure_dir(root/"stage8_sensitivity")

    pace=pd.read_csv(root/"stage3_pace"/"SUBJECT_ORGAN_AGING_PACE.tsv.gz",
                     sep="\t",compression="infer",low_memory=False)
    panel=pd.read_csv(root/"stage1_longitudinal"/"LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz",
                      sep="\t",compression="infer",low_memory=False)
    cov=(panel.sort_values(["person_id","visit_index"]).drop_duplicates("person_id")
         [["person_id","age","sex_male"]].rename(columns={"age":"baseline_age"}))
    pace=pace.merge(cov,on="person_id",how="left")

    # Sex-stratified distribution checks.
    sex_rows=[]
    for (organ,sex),g in pace.groupby(["organ","sex_male"],dropna=False):
        x=pd.to_numeric(g["pace_z_within_organ"],errors="coerce").dropna()
        if len(x)<30:
            continue
        sex_rows.append({
            "organ":organ,"sex_male":sex,"n":len(x),"mean":x.mean(),"sd":x.std(ddof=1),
            "median":x.median(),"q25":x.quantile(.25),"q75":x.quantile(.75)
        })
    write_table(pd.DataFrame(sex_rows),out/"SEX_STRATIFIED_PACE.tsv")

    # Complete-case vs available-case multi-organ summary.
    wide=pace.pivot_table(index="person_id",columns="organ",values="pace_z_within_organ",aggfunc="first")
    norg=wide.notna().sum(axis=1)
    sens=pd.DataFrame({"person_id":wide.index,"n_organs":norg.values})
    sens["available_case_mean"]=wide.mean(axis=1,skipna=True).values
    complete=wide.dropna()
    cc_map=complete.mean(axis=1).to_dict()
    sens["complete_case_mean"]=sens.person_id.map(cc_map)
    sens["available_case_z"]=zscore(sens.available_case_mean)
    sens["complete_case_z"]=zscore(sens.complete_case_mean)
    write_table(sens,out/"COMPLETE_VS_AVAILABLE_CASE.tsv.gz")

    # Leave-one-organ-out composite stability.
    loo=[]
    for organ in wide.columns:
        comp=wide.drop(columns=[organ]).mean(axis=1,skipna=True)
        full=wide.mean(axis=1,skipna=True)
        tmp=pd.concat([full.rename("full"),comp.rename("loo")],axis=1).dropna()
        corr=tmp.corr().iloc[0,1] if len(tmp)>=30 else np.nan
        loo.append({"left_out_organ":organ,"n":len(tmp),"corr_with_full":corr})
    write_table(pd.DataFrame(loo),out/"LEAVE_ONE_ORGAN_OUT.tsv")

    # Visit-count sensitivity.
    visit_rows=[]
    for min_v in [3,4,5]:
        g=pace[pace.n_visits>=min_v]
        visit_rows.append({
            "min_visits":min_v,"subject_organ_rows":len(g),
            "subjects":g.person_id.nunique(),"organs":g.organ.nunique(),
            "median_abs_pace":pd.to_numeric(g.pace_z_within_organ,errors="coerce").abs().median()
        })
    write_table(pd.DataFrame(visit_rows),out/"VISIT_COUNT_SENSITIVITY.tsv")

    info={
        "status":"ok",
        "complete_case_subjects":int(len(complete)),
        "available_case_subjects":int(len(wide)),
        "organs":list(wide.columns),
        "note":"These checks are descriptive sensitivity analyses; inferential models require a frozen analysis plan."
    }
    json_dump(info,out/"STAGE8_SUMMARY.json")
    print(info)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
