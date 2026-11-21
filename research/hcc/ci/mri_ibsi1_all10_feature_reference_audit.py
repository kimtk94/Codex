#!/usr/bin/env python3
"""HCC IBSI-1 ORIGINAL digital phantom: compare all 10 locked MRI features.

The IBSI feature references were explicitly transcribed from the official
Image Features reference tables (document URL below). Each comparison is
PASS/REVIEW, not overall IBSI certification. A numeric mismatch is a
scientific REVIEW result and must never be hidden by changing thresholds.
The analysis uses 100% original digital phantom input without interpolation,
normalization or intensity resegmentation. PyRadiomics v3.1.0 pinned.

The HCC clinical pilot used different settings: binWidth25/normalization.
Clinical image-to-tissue pairing remains NOT_ASSESSED, 12 analyses not run.
"""
import argparse,csv,json,math
from datetime import datetime,timezone
from pathlib import Path
from mri_ibsi1_official_phantom_benchmark import (
  source_info,find_original_files,verify_phantom,SETTINGS
)

VERSION="IBSI1_10_FROZEN_HCC_FEATURES_v1"
REF_DOC="https://ibsi.readthedocs.io/en/master/03_Image_features.html"
# IBSI digital phantom values, IBSl codes and documented tolerances:
# IBSI morphological published tolerances are used as reported.
# "—" means IBSI table doesn't publish a numeric tolerance; for these
# diagnostic checks, use 0.015 absolute on 2 decimal references or
# 0.005 absolute for integer references. This is our own test bound,
# never claimed IBSI-approved.
# Sphericity, elongation and surface-area use IBSI mesh/PCA conventions.
BENCHMARKS={
 "original_shape_VoxelVolume":("YEKZ",592.,4.,"IBSI_OFFICIAL"),
 "original_shape_SurfaceArea":("C0JK",388.,3.,"IBSI_OFFICIAL"),
 "original_shape_Sphericity":("QCFX",0.843,0.005,"IBSI_OFFICIAL"),
 "original_shape_Elongation":("Q3CK",0.816,0.005,"IBSI_OFFICIAL"),
 "original_firstorder_Mean":("Q4LE",2.15,0.015,"DIAGNOSTIC_NOT_IBSI"),
 "original_firstorder_Median":("Y12H",1.,0.005,"DIAGNOSTIC_NOT_IBSI"),
 "original_firstorder_Entropy":("TLU2",1.27,0.015,"DIAGNOSTIC_NOT_IBSI"),
 "original_firstorder_InterquartileRange":("SALO",3.,0.005,"DIAGNOSTIC_NOT_IBSI"),
 "original_glcm_Contrast":("ACUI",5.32,0.015,"DIAGNOSTIC_NOT_IBSI"),
 "original_glcm_JointEntropy":("TU9B",2.4,0.015,"DIAGNOSTIC_NOT_IBSI"),
}
FEATURES={
 "shape":["VoxelVolume","SurfaceArea","Sphericity","Elongation"],
 "firstorder":["Mean","Median","Entropy","InterquartileRange"],
 "glcm":["Contrast","JointEntropy"]
}
FIELDS=("feature","ibsi_code","reference","observed","absolute_difference",
        "tolerance","tolerance_type","status","source_definition",
        "reference_source","software","software_version",
        "clinical_eligibility","mri_rna_tests_run")

def run_measure(folder):
    import radiomics
    from radiomics import featureextractor
    if radiomics.__version__.lstrip("v")!="3.1.0":
        raise ValueError("PyRadiomics version changed; pin exact v3.1.0")
    src=source_info(folder)
    image,mask=find_original_files(folder)
    source_mask_qc=verify_phantom(image,mask)
    settings={**SETTINGS,"binWidth":1.0,"preCrop":False}
    x=featureextractor.RadiomicsFeatureExtractor(**settings)
    x.disableAllImageTypes();x.enableImageTypeByName("Original")
    x.disableAllFeatures();x.enableFeaturesByName(**FEATURES)
    result=x.execute(str(image),str(mask),label=1)
    rows=[]
    for feat,(code,ref,tol,kind) in BENCHMARKS.items():
        obs=float(result[feat])
        if not math.isfinite(obs):raise ValueError("Nonfinite value in "+feat)
        delta=abs(obs-ref)
        rows.append({
          "feature":feat,"ibsi_code":code,"reference":ref,
          "observed":round(obs,10),"absolute_difference":round(delta,10),
          "tolerance":tol,"tolerance_type":kind,
          "status":"PASS" if delta<=tol else "REVIEW_REFERENCE_DEVIATION",
          "source_definition":"IBSI1_DIGITAL_PHANTOM_3D_AVG" if feat.startswith("original_glcm") else
            "IBSI1_DIGITAL_PHANTOM_3D_POOLED",
          "reference_source":REF_DOC,
          "software":"PyRadiomics","software_version":radiomics.__version__,
          "clinical_eligibility":"NOT_ASSESSED","mri_rna_tests_run":"NO"
        })
    if len(rows)!=10:raise ValueError("Ten-feature manifest changed")
    summary={
      "status":"PASS_ALL_10_EXTRACTED_WITH_EXPLICIT_REVIEW" if len(rows)==10 else "FAIL_FEATURES_MISSING",
      "source":src,"source_mask_qc":source_mask_qc,
      "software":"PyRadiomics","software_version":radiomics.__version__,
      "settings":settings,
      "frozen_ten_feature_count":len(rows),
      "reference_matched_count":sum(r["status"]=="PASS" for r in rows),
      "reference_review_count":sum(r["status"]!="PASS" for r in rows),
      "reference_review_features":[r["feature"] for r in rows if r["status"]!="PASS"],
      "comparison_type":"IBSI1_DIGITAL_PHANTOM_SPECIFIC_ONLY",
      "all_10_IBSI_compliant":sum(r["status"]=="PASS" for r in rows)==10,
      "full_IBSI_standardization_certified":False,
      "source_document":REF_DOC,
      "no_MRI_RNA_tests":True,
      "clinical_14_eligible_n":"NOT_ASSESSED",
      "manuscript_claim_ceiling":"S0",
      "generated_utc":datetime.now(timezone.utc).isoformat()
    }
    return rows,summary

def offline_test():
    assert len(BENCHMARKS)==10
    assert set(BENCHMARKS)=={f"original_{family}_{feature}" for family,names in FEATURES.items() for feature in names}
    assert BENCHMARKS["original_glcm_Contrast"][1]==5.32
    assert BENCHMARKS["original_glcm_JointEntropy"][1]==2.4
    assert BENCHMARKS["original_firstorder_Entropy"][1]==1.27
    assert BENCHMARKS["original_shape_VoxelVolume"][1]==592.
    assert BENCHMARKS["original_shape_SurfaceArea"][1]==388.
    assert BENCHMARKS["original_shape_Sphericity"][1]==.843
    assert BENCHMARKS["original_shape_Elongation"][1]==.816
    assert SETTINGS["normalize"] is False and SETTINGS["resampledPixelSpacing"] is None
    print("HCC_IBSI1_TEN_FEATURE_REFERENCE_REGISTRY_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--repo-dir",default="artifacts/ibsi_original_repo")
    p.add_argument("--out-dir",default="artifacts/hcc_ibsi10")
    a=p.parse_args()
    if a.offline_test:return offline_test()
    rows,s=run_measure(a.repo_dir)
    folder=Path(a.out_dir);folder.mkdir(parents=True,exist_ok=True)
    with (folder/"hcc_ibsi1_10_feature_reference_comparison.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (folder/"hcc_ibsi1_10_feature_summary.json").write_text(
        json.dumps(s,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":s["status"],"reference_matched_count":s["reference_matched_count"],
                      "reference_review_count":s["reference_review_count"],
                      "reference_review_features":s["reference_review_features"],
                      "full_IBSI_standardization_certified":False},ensure_ascii=False))
if __name__=="__main__":main()
