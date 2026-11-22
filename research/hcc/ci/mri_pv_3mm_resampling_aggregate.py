#!/usr/bin/env python3
"""Aggregate 14 HCC PV MRI cases native vs 3-mm resampled PyRadiomics.

MRI-only technical quality assurance; no RNA scores, no biological outcome,
no analysis sample exclusions. Reverify native ICC against frozen 2026-10-30
ICC(A,1) before evaluating new resampling and single-case leverage effects.
"""
import argparse,csv,json,math,statistics
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from mri_pv_3mm_resampling_sensitivity import (
    COLS,FEATURE_NAMES,RATERS,ISOTROPIC_MM,validate_rows
)
from mri_pv_pyradiomics_rater_icc import absolute_agreement_icc

REFERENCE="research/hcc/HCC_MRI_PV_RATER_ICC_14_FEATURE_STABILITY_20261030.csv"
PATIENTS="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
SHARD_FILES=(
 "artifacts/hcc_resample/shard0/hcc_pv_native_3mm_features_shard0.csv",
 "artifacts/hcc_resample/shard1/hcc_pv_native_3mm_features_shard1.csv",
)
FEATURE_FIELDS=("feature","native_icc_a1","frozen_icc_a1",
 "resampled_3mm_icc_a1","icc_change_resampled_minus_native",
 "patient_mean_feature_spearman_rho","native_to_3mm_median_absolute_relative_change",
 "native_to_3mm_max_absolute_relative_change",
 "max_difference_patient","reader_reliability_native_frozen",
 "reader_reliability_resampled_descriptive","primary_feature_locked")
CASE_FIELDS=("patient_id","tumor_number","native_z_mm",
 "rater1_roi_volume_native_ml","rater1_roi_volume_resampled_ml",
 "rater1_grid_volume_relative_change_pct",
 "rater2_roi_volume_native_ml","rater2_roi_volume_resampled_ml",
 "rater2_grid_volume_relative_change_pct",
 "entropy_rater1_absolute_relative_change","glcm_contrast_rater1_absolute_relative_change",
 "iqr_rater1_absolute_relative_change",
 "native_high_anisotropy","clinical_eligibility")

def table(path):
    with Path(path).open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def ranks(x):
    """Deterministic average ranks of tied values, not an association with RNA."""
    a=np.array(x,dtype=float); order=np.argsort(a,kind="stable")
    out=np.empty(len(a),dtype=float)
    j=0
    while j<len(a):
        k=j+1
        while k<len(a) and a[order[k]]==a[order[j]]:k+=1
        out[order[j:k]]=0.5*(j+k-1)+1
        j=k
    return out

def rho(x,y):
    a,b=ranks(x),ranks(y)
    if np.std(a)==0 or np.std(b)==0:
        return None
    return float(np.corrcoef(a,b)[0,1])

def relative(a,b):
    return abs(b-a)/max(abs(a),1e-8)

def aggregate(rows,reference,expected):
    if len(rows)!=28 or {r["patient_id"] for r in rows}!=set(expected):
        raise ValueError("Require 14 distinct frozen patients and two reader rows")
    by_key={}
    for r in rows:
        k=(r["patient_id"],r["rater"])
        if k in by_key or r["rater"] not in RATERS:
            raise ValueError("Duplicate/invalid reader case")
        by_key[k]=r
    if len(by_key)!=28 or set(x["feature"] for x in reference)!=set(FEATURE_NAMES):
        raise ValueError("Incorrect radiomics case/feature coverage")
    frozen={r["feature"]:r for r in reference}
    features=[];cases=[]
    ids=sorted(expected)
    for f in FEATURE_NAMES:
        native=np.array([[float(by_key[pid,r]["native__"+f]) for r in RATERS] for pid in ids])
        new=np.array([[float(by_key[pid,r]["resampled__"+f]) for r in RATERS] for pid in ids])
        old_icc=absolute_agreement_icc(native)
        target=float(frozen[f]["icc_a1_absolute_agreement"])
        if abs(old_icc-target)>0.003:
            raise ValueError(f"Native PyRadiomics source drift against original frozen ICC {f}: {old_icc} != {target}")
        new_icc=absolute_agreement_icc(new)
        rank=rho(native.mean(axis=1),new.mean(axis=1))
        errs=[statistics.mean(relative(float(native[i,j]),float(new[i,j]))
                                  for j in range(2)) for i in range(len(ids))]
        imax=int(np.argmax(errs))
        features.append({
            "feature":f,
            "native_icc_a1":round(old_icc,6),
            "frozen_icc_a1":target,
            "resampled_3mm_icc_a1":round(new_icc,6),
            "icc_change_resampled_minus_native":round(new_icc-old_icc,6),
            "patient_mean_feature_spearman_rho":"" if rank is None else round(rank,6),
            "native_to_3mm_median_absolute_relative_change":round(statistics.median(errs),6),
            "native_to_3mm_max_absolute_relative_change":round(max(errs),6),
            "max_difference_patient":ids[imax],
            "reader_reliability_native_frozen":frozen[f]["reliability_screen"],
            "reader_reliability_resampled_descriptive":"ICC_GE_0.90" if new_icc>=.9 else "ICC_BELOW_0.90",
            "primary_feature_locked":"YES" if f in (
                "original_firstorder_Entropy","original_glcm_Contrast",
                "original_firstorder_InterquartileRange") else "NO",
        })
    for pid in ids:
        r=by_key[pid,"rater1"];r2=by_key[pid,"rater2"]
        for item in (r,r2):
            if item["clinical_eligibility"]!="HOLD_UNRESOLVED_NOT_EXCLUDED":
                raise ValueError("No clinical eligibility promotion allowed")
            if float(item["isotropic_spacing_mm"])!=3.0:
                raise ValueError("Different interpolation target")
        def vol(item):
            old=float(item["native_roi_volume_ml"])
            new=int(item["estimated_grid_roi_voxels_3mm"])*(3.0**3)/1000.
            return old,new,100*(new/old-1)
        o1,n1,d1=vol(r)
        o2,n2,d2=vol(r2)
        cases.append({
            "patient_id":pid,"tumor_number":r["selected_tumor_number"],
            "native_z_mm":float(r["voxel_spacing_mm"].split("x")[-1]),
            "rater1_roi_volume_native_ml":round(o1,6),
            "rater1_roi_volume_resampled_ml":round(n1,6),
            "rater1_grid_volume_relative_change_pct":round(d1,4),
            "rater2_roi_volume_native_ml":round(o2,6),
            "rater2_roi_volume_resampled_ml":round(n2,6),
            "rater2_grid_volume_relative_change_pct":round(d2,4),
            "entropy_rater1_absolute_relative_change":round(relative(
                float(r["native__original_firstorder_Entropy"]),
                float(r["resampled__original_firstorder_Entropy"])),6),
            "glcm_contrast_rater1_absolute_relative_change":round(relative(
                float(r["native__original_glcm_Contrast"]),
                float(r["resampled__original_glcm_Contrast"])),6),
            "iqr_rater1_absolute_relative_change":round(relative(
                float(r["native__original_firstorder_InterquartileRange"]),
                float(r["resampled__original_firstorder_InterquartileRange"])),6),
            "native_high_anisotropy":"YES" if pid=="TCGA-BC-A10Y" else "NO",
            "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
        })
    if next(c for c in cases if c["patient_id"]=="TCGA-BC-A10Y")["tumor_number"]!="3":
        raise ValueError("A10Y chosen index tumor3 reverted")
    return features,cases,{
        "status":"PASS_14_CASE_2_READER_NATIVE_VS_3MM_TECHNICAL_SENSITIVITY",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "patient_count":14,"two_reader_extraction_rows":28,
        "feature_count":10,"conditions":["NATIVE_UNCHANGED","3MM_ISOTROPIC_BSPLINE_IMAGE_NEAREST_NEIGHBOR_MASK"],
        "native_frozen_icc_reproduced":10,
        "resampled_icc_ge_0_90":sum(float(x["resampled_3mm_icc_a1"])>=.9 for x in features),
        "n_features_with_resampled_icc_below_native":sum(float(x["icc_change_resampled_minus_native"])<0 for x in features),
        "n_features_with_patient_mean_rank_rho_below_0_8":sum(
            x["patient_mean_feature_spearman_rho"]!="" and
            float(x["patient_mean_feature_spearman_rho"])<.8 for x in features),
        "highest_native_throughplane_anisotropy_case":"TCGA-BC-A10Y",
        "high_anisotropy_z_mm":10.8,
        "A10Y_is_reviewer_flag_not_exclusion":True,
        "clinical_eligible_n":"NOT_ASSESSED",
        "clinical_timing_verified":False,
        "same_exact_MRI_and_RNA_lesion_verified":False,
        "mri_rna_association_computed":False,
        "claim_level":"S0",
        "notes":[
            "Features and ICC here are imaging-only technical measurements, not the MRI-RNA 12-test family.",
            "3mm isotropic interpolation cannot recover details lost by original 10.8mm through-plane acquisition.",
            "Within-patient relative feature changes with low or zero native denominator may be unstable and must be reviewed in absolute units.",
            "This is within-image sensitivity, not IBSI phantom validation or external scanner/sequence generalizability.",
        ]
    }

def offline_test():
    ids=[f"TCGA-AA-{i:04d}" for i in range(14)]
    assert abs(rho([1,2,3,4],[4,3,2,1])+1)<1e-12
    assert rho([1,1,2],[1,2,3]) is not None
    assert rho([1,1,1],[3,2,1]) is None
    assert relative(100,110)==0.1
    print("HCC_PV_NATIVE_VS_3MM_AGGREGATOR_OFFLINE_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--shard-dir",default="artifacts/hcc_resample")
    ap.add_argument("--out-dir",default="artifacts/hcc_resample_final")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    source={}
    with open(PATIENTS,encoding="utf-8",newline="") as f:
        expected={r["patient_id"] for r in csv.DictReader(f)}
    rows=[]
    for i in (0,1):
        path=Path(args.shard_dir)/f"shard{i}"/f"hcc_pv_native_3mm_features_shard{i}.csv"
        with path.open(encoding="utf-8",newline="") as f:
            rr=list(csv.DictReader(f))
        if len(rr)!=14:
            raise ValueError(f"Shard {i} not 7 patients × 2 readers")
        rows.extend(rr)
    features,cases,report=aggregate(rows,table(REFERENCE),expected)
    target=Path(args.out_dir);target.mkdir(parents=True,exist_ok=True)
    for filename,contents,fields in (
        ("hcc_pv_14x2_native_3mm_feature_pairs.csv",rows,COLS),
        ("hcc_pv_10_feature_icc_native_resampled.csv",features,FEATURE_FIELDS),
        ("hcc_pv_14_case_3mm_roi_change.csv",cases,CASE_FIELDS)
    ):
        with (target/filename).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader();w.writerows(contents)
    (target/"hcc_pv_resampling_3mm_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
