#!/usr/bin/env python3
"""Fail-closed immutable source bootstrap reference audit, all 10 MRI features.

Compare new source-only CI CSVs against committed 2026-10-31 actual 14-patient
4,000 paired-bootstrap reference values. Do not interpret as biological results.
"""
import argparse,csv,json,math
from pathlib import Path

ROOT=Path("research/hcc")
FEATURES=ROOT/"HCC_MRI14_SOURCE_PAIRED_BOOTSTRAP_10_FEATURE_FROZEN_20261031.csv"
ICCS=ROOT/"HCC_MRI14_SOURCE_PAIRED_BOOTSTRAP_10_ICC_DELTA_FROZEN_20261031.csv"
LOCKED={"original_firstorder_Entropy","original_firstorder_InterquartileRange","original_glcm_Contrast"}
GENERATED_FEATURE="HCC_MRI14_SOURCE_PAIRED_10_FEATURE_BOOTSTRAP_CI.csv"
GENERATED_ICC="HCC_MRI14_SOURCE_PAIRED_10_ICC_DELTA_BOOTSTRAP_CI.csv"
FIELDS_FEATURE={
 "median_abs_change_pct":"median_abs_pct",
 "ci95_abs_low":"median_abs_pct_ci95_low",
 "ci95_abs_high":"median_abs_pct_ci95_high",
 "median_signed_pct":"median_signed_pct",
 "ci95_signed_low":"median_signed_pct_ci95_low",
 "ci95_signed_high":"median_signed_pct_ci95_high",
 "source_rank_spearman":"spearman_patient_mean_raw_vs_registered",
 "ci95_rho_low":"spearman_ci95_low",
 "ci95_rho_high":"spearman_ci95_high"}
FIELDS_ICC={
 "raw_pv_icc_a1":"raw_icc_A1",
 "registered_pv_icc_a1":"registered_icc_A1",
 "registered_minus_raw_icc_delta":"registered_minus_raw_icc_A1",
 "bootstrap_delta_ci95_low":"paired_boot_icc_difference_ci95_low",
 "bootstrap_delta_ci95_high":"paired_boot_icc_difference_ci95_high"}

def read(path):
    with path.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))

def indexed(rows):
    if len(rows)!=10:
        raise ValueError("EXACT_10_FROZEN_FEATURE_ROWS_REQUIRED")
    out={r["feature"]:r for r in rows}
    if len(out)!=10:raise ValueError("DUPLICATED_FEATURE_KEY")
    return out

def equal_numeric(a,b):
    aa,bb=float(a),float(b)
    return math.isfinite(aa) and math.isfinite(bb) and abs(aa-bb)<=1.5e-6

def frozen_integrity():
    a=indexed(read(FEATURES));b=indexed(read(ICCS))
    if set(a)!=set(b):raise ValueError("FROZEN_FEATURE_AND_ICC_FAMILIES_DIFFER")
    if {name for name,r in a.items() if r["locked_MRI_feature"]=="YES"}!=LOCKED:
        raise ValueError("FROZEN_LOCKED_THREE_FEATURE_FAMILY_CHANGED")
    if {name for name,r in b.items() if r["locked_MRI_feature"]=="YES"}!=LOCKED:
        raise ValueError("FROZEN_ICC_LOCKED_FEATURE_FAMILY_CHANGED")
    for name,r in a.items():
        if (r["n_patients"]!="14" or r["bootstrap_seed"]!="20261031"
           or r["paired_patient_bootstrap"]!="4000"
           or r["biological_tests_executed"]!="0" or r["claim_ceiling"]!="S0"):
            raise ValueError("FROZEN_SOURCE_BOOTSTRAP_PROVENANCE_CHANGED")
        if float(r["ci95_abs_low"])>float(r["median_abs_change_pct"]) or float(r["ci95_abs_high"])<float(r["median_abs_change_pct"]):
            raise ValueError("FROZEN_SOURCE_CI_EXCLUDES_OBSERVED_ESTIMATE")
    for name,r in b.items():
        if (r["n_patients"]!="14" or r["paired_patient_bootstrap"]!="4000"
            or r["valid_paired_bootstrap"]!="4000"
            or r["biological_tests_executed"]!="0" or r["claim_ceiling"]!="S0"):
            raise ValueError("FROZEN_ICC_DELTA_PROVENANCE_CHANGED")
        if float(r["bootstrap_delta_ci95_low"])>float(r["bootstrap_delta_ci95_high"]):
            raise ValueError("FROZEN_ICC_DELTA_INVALID_CI")
    for name in ("VoxelVolume","SurfaceArea","Sphericity","Elongation"):
        n="original_shape_"+name
        if not all(equal_numeric(a[n][x],0.0) for x in ("median_abs_change_pct","ci95_abs_low","ci95_abs_high")):
            raise ValueError("MASK_SHAPE_NEGATIVE_CONTROL_CHANGED")
        if not all(equal_numeric(b[n][x],0.0) for x in ("registered_minus_raw_icc_delta","bootstrap_delta_ci95_low","bootstrap_delta_ci95_high")):
            raise ValueError("MASK_SHAPE_ICC_NEGATIVE_CONTROL_CHANGED")
    if not equal_numeric(a["original_glcm_Contrast"]["median_abs_change_pct"],22.079911):
        raise ValueError("FROZEN_GLCM_SOURCE_22_PERCENT_REFERENCE_CHANGED")
    return a,b

def cross_validate(out):
    static_features,static_icc=frozen_integrity()
    current_feature=indexed(read(out/GENERATED_FEATURE))
    current_icc=indexed(read(out/GENERATED_ICC))
    if set(static_features)!=set(current_feature) or set(static_icc)!=set(current_icc):
        raise ValueError("GENERATED_FEATURE_UNIVERSE_OR_INDEX_DRIFT")
    for name,r in static_features.items():
        current=current_feature[name]
        for old,new in FIELDS_FEATURE.items():
            if not equal_numeric(r[old],current[new]):
                raise ValueError("ORIGINAL_4000_BOOTSTRAP_SOURCE_CI_CHANGED:"+name+":"+old)
        if (r["n_patients"]!=current["n_independent_patients"] or
            r["paired_patient_bootstrap"]!=current["n_paired_bootstrap"] or
            (r["locked_MRI_feature"]=="YES")!=(current["locked_primary_MRI_feature"]=="True") or
            int(current["n_cases_abs_pct_ge10"])!=int(r["cases_abs_ge10pct"]) or
            int(current["n_cases_abs_pct_ge20"])!=int(r["cases_abs_ge20pct"])):
            raise ValueError("SOURCE_BOOTSTRAP_SAMPLES_OR_OUTCOMES_CHANGED")
    for name,r in static_icc.items():
        current=current_icc[name]
        for old,new in FIELDS_ICC.items():
            if not equal_numeric(r[old],current[new]):
                raise ValueError("ORIGINAL_4000_BOOTSTRAP_ICC_DELTA_CHANGED:"+name+":"+old)
        if (r["n_patients"]!=current["n_patients"] or
            r["paired_patient_bootstrap"]!=current["bootstrap"] or
            r["valid_paired_bootstrap"]!=current["valid_bootstrap_count"] or
            (r["locked_MRI_feature"]=="YES")!=(current["locked_primary_MRI_feature"]=="True")):
            raise ValueError("ICC_BOOTSTRAP_SOURCE_REFERENCE_CHANGED")
    meta=json.loads((out/"HCC_MRI14_SOURCE_BOOTSTRAP_UNCERTAINTY_METADATA.json").read_text())
    if (meta["MRI_RNA_12_tests"]!="NOT_EXECUTED" or meta["claim_ceiling"]!="S0"
        or meta["qualified_RNA_matched_n"]!="NOT_ASSESSED"
        or meta["bootstrap_seed"]!=20261031 or meta["n_paired_patient_resamples"]!=4000
        or meta["n_independent_patients"]!=14 or meta["biological_p_value_computed"]):
        raise ValueError("CLINICAL_OR_FROZEN_BOOTSTRAP_CONTRACT_CHANGED")
    return len(static_features),len(static_icc)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--generated-dir",type=Path)
    args=ap.parse_args()
    if args.generated_dir is None:
        a,b=frozen_integrity()
        print("HCC_MRI14_PERMANENT_10_FEATURE_10_ICC_DELTA_SOURCE_BOOTSTRAP_REFERENCE_PASS",len(a),len(b))
    else:
        a,b=cross_validate(args.generated_dir)
        print("HCC_MRI14_GENERATED_ALL_10_SOURCE_CI_AND_ICC_CI_MATCH_FROZEN_REFERENCES_PASS",a,b)

if __name__=="__main__":main()
