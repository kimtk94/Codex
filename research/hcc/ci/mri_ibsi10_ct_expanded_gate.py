#!/usr/bin/env python3
"""Combine official IBSI-1 ten-feature and CT source jobs into scientific gate.

A failed/unstable feature reference is REVIEW, and never interpreted as full
IBSI feature profile validation. CT hashes match across IBSI1/IBSI2 upstream,
but IBSI1 CT config A-E and IBSI2 filtered feature tasks are unexecuted.
No patient-level RNA data or biological MRI features are accessed.
"""
import argparse,csv,json,math
from datetime import datetime,timezone
from pathlib import Path

FEATURE_FILE="artifacts/hcc_ibsi10/hcc_ibsi1_10_feature_reference_comparison.csv"
FEATURE_SUM="artifacts/hcc_ibsi10/hcc_ibsi1_10_feature_summary.json"
CT_SUM="artifacts/hcc_ibsi_ct/hcc_ibsi1_ibsi2_ct_source_provenance_and_config_readiness.json"
PRIOR="research/hcc/HCC_IBSI1_OFFICIAL_PHANTOM_GLCM_VALIDATION_20261031.json"
CASE="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
LEDGER="research/hcc/HCC_VERIFICATION_LEDGER.csv"
FEATURES={
 "original_shape_VoxelVolume","original_shape_SurfaceArea",
 "original_shape_Sphericity","original_shape_Elongation",
 "original_firstorder_Mean","original_firstorder_Median",
 "original_firstorder_Entropy","original_firstorder_InterquartileRange",
 "original_glcm_Contrast","original_glcm_JointEntropy",
}

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def load_csv(path):
    with Path(path).open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))

def combine(source,features,ct,previous,cases,ledger):
    if source["source"]["official_source_commit_sha"]!=previous["official_repository_commit"]:
        raise ValueError("Official digital phantom version not pinned")
    for k,path in (("image_sha256","image_sha256"),("mask_sha256","mask_sha256")):
        if source["source"][k]!=previous[k]:
            raise ValueError("Original IBSI digital source drift")
    if source["source_mask_qc"]["original_roi_voxels"]!=74:
        raise ValueError("Official IBSI1 phantom ROI changed")
    if len(features)!=10 or {r["feature"] for r in features}!=FEATURES:
        raise ValueError("10 locked HCC features not all measured")
    if any(r["clinical_eligibility"]!="NOT_ASSESSED" or r["mri_rna_tests_run"]!="NO" for r in features):
        raise ValueError("Benchmark may not enroll or test HCC patients")
    if source["reference_matched_count"]+source["reference_review_count"]!=10:
        raise ValueError("Benchmark must report all reference statuses")
    if (source["reference_matched_count"]!=sum(r["status"]=="PASS" for r in features)
        or source["reference_review_count"]!=sum(r["status"]=="REVIEW_REFERENCE_DEVIATION" for r in features)):
        raise ValueError("Incorrect status counts")
    if source.get("full_IBSI_standardization_certified") is not False:
        raise ValueError("IBSI 10-feature compare does not certify whole feature/preprocessing profile")
    if source["software_version"].lstrip("v")!="3.1.0":
        raise ValueError("Unpinned PyRadiomics")
    contrast=next(r for r in features if r["feature"]=="original_glcm_Contrast")
    if abs(float(contrast["observed"])-previous["pyradiomics"]["contrast"])>1e-7:
        raise ValueError("Previously verified IBSI1 Contrast no longer reproduces")
    if (ct["status"]!="PASS_ORIGINAL_IBSI1_AND_IBSI2_CT_NIFTI_IDENTICAL_SOURCE"
        or ct["source_commit_sha"]!=previous["official_repository_commit"]
        or len(ct["original_ct_sources"])!=2):
        raise ValueError("CT originals missing or source version changed")
    if any(ct[x] is not False for x in (
         "IBSI_1_phase_II_preprocessing_reproduced",
         "IBSI_2_phase_II_filtered_feature_benchmark_reproduced",
         "full_IBSI_compliance")):
        raise ValueError("CT source audit must not claim actual preprocessing/features ran")
    if len(cases)!=14 or len({r["patient_id"] for r in cases})!=14:
        raise ValueError("HCC frozen candidate identity/denominator change")
    gates={r["id"]:r["status"] for r in ledger}
    if any(gates[x]!="PARTIAL" for x in ("HCC-13","HCC-18")) or gates["HCC-20"]!="PENDING":
        raise ValueError("HCC clinical or scientific inference automatically promoted")
    statuses={r["feature"]:r["status"] for r in features}
    return {
      "status":("PASS_SOURCE_ALL_10_IBSI_PHANTOM_MATCHED" if source["reference_review_count"]==0
                else "REVIEW_IBSI_FEATURE_DEFINITION_OR_SOFTWARE_DEVIATIONS"),
      "source_acquisition":"PASS",
      "ibsi1_digital_10_extracted_count":10,
      "ibsi1_reference_match_count":source["reference_matched_count"],
      "ibsi1_reference_review_count":source["reference_review_count"],
      "ibsi1_per_feature_status":statuses,
      "ibsi2_ct_original_same_as_ibsi1_ct":True,
      "IBSI_1_CT_config_A_E":"HOLD_NOT_EXECUTED",
      "IBSI_2_CT_filtered_phantom":"HOLD_NOT_EXECUTED",
      "ibsi_all_features_and_preprocessing_certified":False,
      "hcc_14_technical_candidates":14,
      "hcc_14_eligible_count":"NOT_ASSESSED",
      "hcc13_18_technical_method":"PARTIAL",
      "hcc20_12_mri_rna_tests":"PENDING_NOT_EXECUTED",
      "claim_ceiling":"S0",
      "comparison_references":"https://ibsi.readthedocs.io/en/master/03_Image_features.html",
      "review_notes":[
         "Digital phantom 'PASS' evaluates only the given IBSI-1 10 feature values and pinned PyRadiomics settings.",
         "CT source SHA/geometry check is not CT preprocessing A-E or IBSI2 filtered response benchmark.",
         "IBSI digital phantom is unnormalized binWidth=1, distinct from HCC PV normalized binWidth=25 cohort."
      ],
      "generated_utc":datetime.now(timezone.utc).isoformat()
    }

def offline_test():
    refs=json.loads(Path(PRIOR).read_text(encoding="utf-8"))
    assert refs["pyradiomics"]["status"]=="PASS_MATCH_TO_IBSI_3D_AVG_REFERENCE"
    assert len(FEATURES)==10
    assert refs["mri_rna_biological_associations"]=="NOT_EXECUTED"
    print("HCC_IBSI10_CT_DUAL_SOURCE_FAIL_CLOSED_INTEGRATION_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_ibsi_expanded")
    a=p.parse_args()
    if a.offline_test:return offline_test()
    results=combine(load_json(FEATURE_SUM),load_csv(FEATURE_FILE),
                    load_json(CT_SUM),load_json(PRIOR),load_csv(CASE),load_csv(LEDGER))
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"hcc_ibsi10_ct_source_joint_review.json").write_text(
        json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(results,ensure_ascii=False))
if __name__=="__main__":main()
