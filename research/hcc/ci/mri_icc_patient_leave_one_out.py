#!/usr/bin/env python3
"""Patient leave-one-out ICC sensitivity on completed 14-patient HCC PV radiomics.

Input is the public-derived numerical PyRadiomics feature table and bootstrap
ICC data (NOT any RNA or image). Outputs feature ICC range and whether reader
reliability is robust to each individual patient. Cannot infer anatomical truth.
"""
import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

EXPECTED=14
RATERS=("rater1","rater2")
FIELDS=("feature","n","icc_original","bootstrap_ci95_low",
        "icc_loo_min","icc_loo_max","min_loo_removed_patient",
        "max_loo_removed_patient","passing_icc_0_75_all_leave_one_out",
        "reliability_decision")


def absolute_icc(arr):
    x=np.asarray(arr,dtype=float)
    if x.ndim!=2 or x.shape[1]!=2 or len(x)<3 or not np.isfinite(x).all():
        raise ValueError("Invalid ICC matrix")
    n,k=x.shape
    g=np.mean(x)
    row=np.mean(x,axis=1);col=np.mean(x,axis=0)
    msr=k*np.sum((row-g)**2)/(n-1)
    msc=n*np.sum((col-g)**2)/(k-1)
    mse=np.sum((x-row[:,None]-col[None,:]+g)**2)/((n-1)*(k-1))
    denom=msr+(k-1)*mse+k*(msc-mse)/n
    if denom<=0 or not math.isfinite(denom):raise ValueError("ICC undefined")
    return float((msr-mse)/denom)


def analyze(features,base,expected=14):
    ids=sorted({x["patient_id"] for x in features})
    if len(ids)!=expected or len(features)!=expected*2:
        raise ValueError(f"Need {expected} distinct patients and two rows each")
    by_pair={}
    for row in features:
        p=(row["patient_id"],row["rater"])
        if p in by_pair or p[1] not in RATERS:
            raise ValueError("Duplicate/unknown reader")
        by_pair[p]=row
    fields=sorted(x for x in features[0] if x.startswith("original_"))
    official={x["feature"]:x for x in base}
    if set(fields)!=set(official):raise ValueError("Feature families differ")
    rows=[]
    for name in fields:
        mat=np.array([[float(by_pair[p,r][name]) for r in RATERS] for p in ids])
        estimate=absolute_icc(mat)
        target=float(official[name]["icc_a1_absolute_agreement"])
        if abs(estimate-target)>0.00002:
            raise ValueError(f"ICC mismatch vs original report {name}: {estimate} vs {target}")
        lo=float(official[name]["bootstrap_ci95_low"])
        loo=[absolute_icc(np.delete(mat,i,axis=0)) for i in range(len(ids))]
        min_i=int(np.argmin(loo)); max_i=int(np.argmax(loo))
        # Conservative screening rule: strong original ICC, bootstrap CI lower
        # >=0.75 and every leave-one-person-out ICC remains >=0.75.
        # This is a reliability-only filter, not RNA outcome selection.
        reliable=(estimate>=0.90 and lo>=0.75 and min(loo)>=0.75)
        rows.append({
            "feature":name,"n":len(ids),"icc_original":round(estimate,5),
            "bootstrap_ci95_low":round(lo,5),
            "icc_loo_min":round(min(loo),5),
            "icc_loo_max":round(max(loo),5),
            "min_loo_removed_patient":ids[min_i],
            "max_loo_removed_patient":ids[max_i],
            "passing_icc_0_75_all_leave_one_out":"YES" if min(loo)>=0.75 else "NO",
            "reliability_decision":("RELIABILITY_SCREEN_PASS" if reliable
                                   else "NOT_FOR_PRIMARY_RELIABILITY_SCREEN"),
        })
    return rows


def offline_test():
    data=[]
    for i in range(14):
        for r in RATERS:
            data.append({"patient_id":f"TCGA-AA-{i:04d}","rater":r,
                         "original_shape_VoxelVolume":float(i+1)+(.01 if r=="rater2" else 0.)})
    base=[{"feature":"original_shape_VoxelVolume",
           "icc_a1_absolute_agreement":str(round(absolute_icc(np.array([
               [float(i+1),float(i+1)+.01] for i in range(14)])),5)),
           "bootstrap_ci95_low":"0.99"}]
    res=analyze(data,base)
    assert len(res)==1
    assert res[0]["reliability_decision"]=="RELIABILITY_SCREEN_PASS"
    try:
        analyze(data[:-1],base)
    except ValueError:pass
    else:raise AssertionError("Missing reader must fail")
    print("HCC_ICC_PATIENT_LEAVE_ONE_OUT_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--features",default="artifacts/hcc_feature_icc/mri_pv_two_reader_radiomics_features.csv")
    ap.add_argument("--icc",default="artifacts/hcc_feature_icc/mri_pv_feature_icc_a1.csv")
    ap.add_argument("--out-dir",default="artifacts/hcc_feature_robustness")
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    def read(path):
        with open(path,encoding="utf-8",newline="") as f:
            return list(csv.DictReader(f))
    rows=analyze(read(args.features),read(args.icc))
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/"mri_pv_icc_patient_leave_one_out.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    passing=[x["feature"] for x in rows
             if x["reliability_decision"]=="RELIABILITY_SCREEN_PASS"]
    report={
        "status":"PASS_PATIENT_LEVEL_ICC_SENSITIVITY_COMPUTED",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "n_patients":14,"n_tested_features":len(rows),
        "reader_stability_screened_features":passing,
        "reader_stability_screen_count":len(passing),
        "thresholds":{"icc_a1_point_min":0.90,"bootstrap_ci95_lower_min":0.75,
                      "every_leave_one_out_min":0.75},
        "notes":[
            "These are reader-reliable features only; high ICC can reflect large between-patient heterogeneity.",
            "Individual exclusion effect is not an independent cohort or a biological effect.",
            "The MRI intensity normalization/binWidth and image spacing methods were frozen before MRI–RNA association.",
            "Pathway hypothesis tests, patient clinical/treatment timing and expert tumor review are still blocked."
        ],
    }
    (out/"mri_pv_icc_patient_leave_one_out_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":
    main()
