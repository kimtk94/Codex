#!/usr/bin/env python3
"""Run on every PR: frozen 14×2 binWidth × 3mm MRI-only factorial QC.

Only checks previously executed/released GLCM technical results.
Expensive original NIfTI 168-cell extraction is not triggered by this check.
Clinical gate and original 12 MRI–RNA tests remain immutable and unexecuted.
"""
import argparse,csv,math
from pathlib import Path

METRICS="research/hcc/HCC_MRI_14_GLCM_BINWIDTH_VOXEL_FACTORIAL_20261031.csv"
CASES="research/hcc/HCC_MRI_14_GLCM_CONTRAST_CASE_FACTORIAL_20261031.csv"
FROZEN="research/hcc/HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv"
LESION="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
FEATURES=(
 "original_glcm_Contrast","original_glcm_JointEntropy",
 "original_firstorder_Entropy","original_firstorder_InterquartileRange")
BIN=(12.5,25.,50.)
SPACINGS=("native","3mm")

def load(path):
    with Path(path).open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))

def check(rows,by_case,reference,lesions):
    expected={(f,s,b) for f in FEATURES for s in SPACINGS for b in BIN}
    keys={(r["feature"],r["spacing_condition"],float(r["binwidth"])) for r in rows}
    if len(rows)!=24 or keys!=expected:raise ValueError("Factorial reference coverage changed")
    refs={r["feature"]:r for r in reference}
    if not set(FEATURES).issubset(refs):raise ValueError("No original paired reference")
    for r in rows:
        feat,space,bw=r["feature"],r["spacing_condition"],float(r["binwidth"])
        if int(r["patient_rater_values"])!=28:raise ValueError("Reader coverage reduced")
        icc=float(r["reader_icc_a1"])
        if not (-1<=icc<=1):raise ValueError("ICC outside range")
        if bw==25.:
            col="native_icc_a1" if space=="native" else "resampled_3mm_icc_a1"
            if abs(icc-float(refs[feat][col]))>1e-4:
                raise ValueError("Baseline source ICC drift")
            if r["baseline_frozen_icc_reproduced"]!="YES":
                raise ValueError("Lack of original ICC provenance")
        else:
            if r["baseline_frozen_icc_reproduced"]!="NOT_BASELINE":
                raise ValueError("Nonreference condition mislabelled")
        for col in ("median_abs_relative_vs_native25",
                    "median_abs_relative_vs_binwidth25_same_spacing"):
            v=float(r[col])
            if not math.isfinite(v) or v<0:
                raise ValueError("Invalid within-case relative sensitivity")
    case_ids={r["patient_id"] for r in by_case}
    frozen_ids={r["patient_id"] for r in lesions}
    if len(by_case)!=14 or len(frozen_ids)!=14 or case_ids!=frozen_ids:
        raise ValueError("Case count or source patient identity changed")
    if sum(r["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED" for r in by_case):
        raise ValueError("Purported patient clinical eligibility promoted")
    c={r["patient_id"]:r for r in by_case}
    if c["TCGA-BC-A10Y"]["native_rater1_b25"]=="":
        raise ValueError("Original high anisotropy source missing")
    glcm={ (r["spacing_condition"],float(r["binwidth"])):r
            for r in rows if r["feature"]=="original_glcm_Contrast"}
    if float(glcm["native",12.5]["median_abs_relative_vs_binwidth25_same_spacing"])<2.5:
        raise ValueError("Key Contrast fixed-bin-width shift changed silently")
    if float(glcm["3mm",25.]["median_abs_relative_vs_native25"])<.7:
        raise ValueError("Key Contrast native-vs-grid sensitivity changed silently")
    iqr=[r for r in rows if r["feature"]=="original_firstorder_InterquartileRange"]
    if any(float(r["median_abs_relative_vs_binwidth25_same_spacing"])!=0. for r in iqr):
        raise ValueError("IQR should be invariant to binWidth in same source grid")
    return True

def offline_test():
    met,case,ref,lesion=load(METRICS),load(CASES),load(FROZEN),load(LESION)
    check(met,case,ref,lesion)
    falsified=[dict(x) for x in case]
    falsified[0]["clinical_eligibility"]="ELIGIBLE"
    try:check(met,falsified,ref,lesion)
    except ValueError:pass
    else:raise AssertionError("Unauthorized patient eligibility upgrade was not blocked")
    print("HCC_GLCM_168_CELL_FROZEN_FACTORIAL_14_PATIENT_CI_GUARD_PASS")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--offline-test",action="store_true")
    args=parser.parse_args()
    offline_test()
if __name__=="__main__":main()
