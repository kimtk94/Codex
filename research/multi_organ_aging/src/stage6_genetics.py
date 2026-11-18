from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
from common import bh_fdr, ensure_dir, json_dump, load_config, write_table, zscore

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--genetics")
    ap.add_argument("--out-dir")
    a=ap.parse_args()
    cfg=load_config(a.config)
    root=Path(a.out_dir or cfg["paths"]["out_dir"])
    out=ensure_dir(root/"stage6_genetics")
    gpath=Path(a.genetics or cfg["paths"]["genetics_file"])
    if not gpath.exists():
        info={"status":"not_run","reason":"genetics_file_missing","path":str(gpath)}
        json_dump(info,out/"STAGE6_SUMMARY.json"); print(info); return 0

    pace=pd.read_csv(root/"stage3_pace"/"SUBJECT_ORGAN_AGING_PACE.tsv.gz",
                     sep="\t",compression="infer",low_memory=False)
    wide=pace.pivot_table(index="person_id",columns="organ",
                          values="pace_z_within_organ",aggfunc="first")
    wide.columns=[f"pace_{c}" for c in wide.columns]
    wide=wide.reset_index()

    smry=pd.read_csv(root/"stage3_pace"/"SUBJECT_MULTI_ORGAN_PACE_SUMMARY.tsv.gz",
                     sep="\t",compression="infer",low_memory=False)
    phen=smry.merge(wide,on="person_id",how="left")
    dpath=root/"stage4_discordance"/"SUBJECT_MULTI_ORGAN_DISCORDANCE_CLUSTER.tsv.gz"
    if dpath.exists():
        dd=pd.read_csv(dpath,sep="\t",compression="infer",low_memory=False)
        phen=phen.merge(dd[["person_id","discordance_sd","discordance_range"]],
                        on="person_id",how="left")

    panel=pd.read_csv(root/"stage1_longitudinal"/"LONGITUDINAL_MULTI_ORGAN_PANEL.tsv.gz",
                      sep="\t",compression="infer",low_memory=False)
    cov=(panel.sort_values(["person_id","visit_index"]).drop_duplicates("person_id")
         [["person_id","age","sex_male"]].rename(columns={"age":"baseline_age"}))
    phen=phen.merge(cov,on="person_id",how="left")

    gen=pd.read_csv(gpath,sep="\t",compression="infer",low_memory=False)
    if "person_id" not in gen.columns:
        raise SystemExit("Genetics file must contain person_id.")
    d=phen.merge(gen,on="person_id",how="inner")

    prs=[c for c in gen.columns if c.lower().startswith(("prs_","pgs_"))]
    pcs=[c for c in gen.columns if c.lower().startswith("pc") and c[2:].isdigit()][:10]
    outcomes=[c for c in d.columns if c.startswith("pace_")]
    outcomes += [c for c in ["multi_organ_pace_z","discordance_sd","discordance_range"] if c in d.columns]

    rows=[]
    for prs_col in prs:
        for outcome in outcomes:
            cols=[outcome,prs_col,"baseline_age","sex_male"]+pcs
            x=d[cols].copy()
            for c in cols:
                x[c]=pd.to_numeric(x[c],errors="coerce")
            x=x.dropna()
            if len(x)<200 or x[prs_col].std(ddof=0)==0 or x[outcome].std(ddof=0)==0:
                continue
            y=zscore(x[outcome])
            X=pd.DataFrame({"prs_z":zscore(x[prs_col]),
                            "baseline_age":x["baseline_age"],
                            "sex_male":x["sex_male"]},index=x.index)
            for pc in pcs:
                X[pc]=x[pc]
            X=sm.add_constant(X,has_constant="add")
            fit=sm.OLS(y,X,missing="drop").fit(cov_type="HC3")
            rows.append({"prs":prs_col,"phenotype":outcome,"n":int(fit.nobs),
                         "beta_per_sd":float(fit.params["prs_z"]),
                         "se":float(fit.bse["prs_z"]),
                         "p":float(fit.pvalues["prs_z"])})
    res=pd.DataFrame(rows)
    if not res.empty:
        res["q_fdr"]=bh_fdr(res["p"])
    write_table(res,out/"PRS_AGING_PACE_ASSOCIATIONS.tsv")
    info={"status":"ok","subjects_merged":int(len(d)),"prs_columns":prs,
          "phenotypes":outcomes,"models_tested":int(len(res)),
          "note":"PRS analyses are association/validation analyses, not Mendelian randomization."}
    json_dump(info,out/"STAGE6_SUMMARY.json"); print(info); return 0

if __name__=="__main__":
    raise SystemExit(main())
