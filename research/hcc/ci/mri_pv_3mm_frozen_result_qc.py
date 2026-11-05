#!/usr/bin/env python3
"""Frozen outcome-blind HCC 14-patient native/3mm MRI measurement sensitivity audit.

Checks that archived measured values correspond to the original reader ICC
snapshot, frozen selected index lesion and clinically unresolved cohort.
This does NOT recompute radiomics from source MRI and is NOT IBSI validation.
"""
import argparse,csv,math
from pathlib import Path

FEATURES="research/hcc/HCC_MRI_PV_14X2_NATIVE_VS_3MM_FEATURE_REPRODUCIBILITY_20261031.csv"
CASES="research/hcc/HCC_MRI_PV_14_NATIVE_3MM_ROI_VOLUME_AND_PRIMARY_FEATURE_CHANGE_20261031.csv"
NATIVE="research/hcc/HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv"
LESIONS="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"

def read(file):
    with Path(file).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def validate(f,c,old,lesion):
    assert len(f)==10 and len(c)==14
    name={r["feature"]:r for r in f}
    baseline={r["feature"]:r for r in old}
    assert set(name)==set(baseline)
    patients={r["patient_id"]:r for r in c}
    frozen={r["patient_id"]:r for r in lesion}
    assert len(patients)==14 and len(frozen)==14 and set(patients)==set(frozen)
    for key,v in name.items():
        assert abs(float(v["frozen_icc_a1"])-float(baseline[key]["icc_a1_absolute_agreement"]))<1e-8
        assert abs(float(v["native_icc_a1"])-float(v["frozen_icc_a1"]))<1e-4
        assert v["reader_reliability_native_frozen"]==baseline[key]["reliability_screen"]
        assert math.isfinite(float(v["resampled_3mm_icc_a1"]))
        assert (v["primary_feature_locked"]=="YES")==(
            key in ("original_firstorder_Entropy","original_firstorder_InterquartileRange","original_glcm_Contrast"))
    for pid,row in patients.items():
        assert row["tumor_number"]==frozen[pid]["representative_tumor_number"]
        assert row["clinical_eligibility"]=="HOLD_UNRESOLVED_NOT_EXCLUDED"
        assert float(row["native_z_mm"])>0
        for col in ("rater1_grid_volume_relative_change_pct","rater2_grid_volume_relative_change_pct",
                    "entropy_rater1_absolute_relative_change","glcm_contrast_rater1_absolute_relative_change",
                    "iqr_rater1_absolute_relative_change"):
            assert math.isfinite(float(row[col]))
    glcm=name["original_glcm_Contrast"]
    assert float(glcm["native_to_3mm_median_absolute_relative_change"])>0.7
    assert float(glcm["patient_mean_feature_spearman_rho"])<0.9
    assert float(name["original_firstorder_Entropy"]["native_to_3mm_median_absolute_relative_change"])<.03
    assert float(name["original_firstorder_InterquartileRange"]["native_to_3mm_median_absolute_relative_change"])<.03
    assert sum(float(x["resampled_3mm_icc_a1"])>=.9 for x in f)==8
    assert patients["TCGA-BC-A10Y"]["native_high_anisotropy"]=="YES"
    assert float(patients["TCGA-BC-A10Y"]["native_z_mm"])==10.8
    assert sum(x["native_high_anisotropy"]=="YES" for x in c)==1
    assert float(patients["TCGA-G3-AAV7"]["rater1_grid_volume_relative_change_pct"])< -5
    return True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    args=p.parse_args()
    validate(read(FEATURES),read(CASES),read(NATIVE),read(LESIONS))
    if args.offline_test:
        data=read(CASES)
        altered=[{**x} for x in data]
        altered[0]["clinical_eligibility"]="ELIGIBLE"
        try:validate(read(FEATURES),altered,read(NATIVE),read(LESIONS))
        except AssertionError:pass
        else:raise AssertionError("Clinical promotion incorrectly passed QC")
    print("HCC_PV_NATIVE_TO_3MM_FROZEN_TECHNICAL_MEASUREMENT_QC_PASS")

if __name__=="__main__":main()
