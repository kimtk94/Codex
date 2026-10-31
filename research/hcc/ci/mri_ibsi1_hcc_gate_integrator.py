#!/usr/bin/env python3
"""Fail-closed triage for official IBSI1 phantom vs 14-case HCC imaging QC.

Clinical and RNA-inference status never promoted by reference-phantom pass.
Mismatch in IBSI benchmark is REVIEW, not silent PASS and not automatically
a tool runtime failure. Missing source/identity/hash is a technical error.
"""
import argparse,csv,json,math
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

SOURCE="artifacts/hcc_ibsi_source/hcc_ibsi1_official_source_manifest.json"
MEASURE="artifacts/hcc_ibsi_measure/hcc_ibsi1_pyradiomics_benchmark.json"
FACTORIAL="research/hcc/HCC_MRI_14_GLCM_BINWIDTH_VOXEL_FACTORIAL_20261031.csv"
CASES="research/hcc/HCC_MRI_14_GLCM_CONTRAST_CASE_FACTORIAL_20261031.csv"
GATES="research/hcc/HCC_VERIFICATION_LEDGER.csv"

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def combined(src,measured):
    for k in ("official_source_commit_sha","image_sha256","mask_sha256"):
        if not src.get(k) or src[k]!=measured.get(k):
            raise ValueError("Source phantom provenance drift "+k)
    if src.get("status")!="PASS_OFFICIAL_NIFTI_SOURCE_PROVENANCE":
        raise ValueError("Official original source manifest failed")
    if measured.get("original_image_roi",{}).get("original_roi_voxels")!=74:
        raise ValueError("IBSI digital phantom ROI should have 74 voxels")
    if measured.get("referenced_IBSI_3d_avg")!=5.32:
        raise ValueError("IBSI contrast 3D avg official reference changed")
    if measured.get("distinct_IBSI_3d_merge_reference_not_tested")!=5.12:
        raise ValueError("IBSI merged variant misreported")
    observed=float(measured["observed_contrast"])
    if not math.isfinite(observed):raise ValueError("Nonfinite IBSI phantom feature")
    if measured["hcc_14_patient_clinical_eligibility"]!="NOT_ASSESSED" or measured["mri_rna_associations_run"] is not False:
        raise ValueError("Benchmark incorrectly promoted HCC clinical eligibility")
    if measured["status"] not in ("PASS_MATCH_TO_IBSI_3D_AVG_REFERENCE",
                                 "REVIEW_SOFTWARE_REFERENCE_DEVIATION"):
        raise ValueError("Unexpected benchmark pass")
    with open(FACTORIAL,encoding="utf-8",newline="") as f:rows=list(csv.DictReader(f))
    with open(CASES,encoding="utf-8",newline="") as f:cases=list(csv.DictReader(f))
    with open(GATES,encoding="utf-8",newline="") as f:gate_rows=list(csv.DictReader(f))
    if len(rows)!=24 or len(cases)!=14 or len({c["patient_id"] for c in cases})!=14:
        raise ValueError("Frozen 14-patient GLCM source denominator changed")
    states={r["id"]:r["status"] for r in gate_rows}
    for key in ("HCC-13","HCC-18"):
        if states.get(key)!="PARTIAL":raise ValueError("IBSI phantom is not full HCC method approval")
    if states.get("HCC-20")!="PENDING":
        raise ValueError("Association tests are still pending")
    return {
      "status":"PASS_REFERENCE_MATH_AND_SOURCE_COHERENCE" if
            measured["status"]=="PASS_MATCH_TO_IBSI_3D_AVG_REFERENCE"
            else "HOLD_IBSI_IMPLEMENTATION_REFERENCE_DEVIATION_REVIEW",
      "benchmark_status":measured["status"],
      "original_official_git_commit":src["official_source_commit_sha"],
      "original_image_sha256":src["image_sha256"],
      "original_mask_sha256":src["mask_sha256"],
      "IBSI_3d_avg_expected":5.32,
      "PyRadiomics_observed":observed,
      "ibsi_diagnostic_diff":measured["signed_difference_from_5_32"],
      "clinical_source_patients":14,
      "HCC13_reader_and_acquisition_status":"PARTIAL",
      "HCC18_ibsi_phantom_status":"BENCHMARK_ONLY_NO_FULL_CERTIFICATION",
      "HCC14_pretreatment":"HOLD",
      "HCC17_eligible_n":"NOT_ASSESSED",
      "HCC20_mri_rna_associations":"PENDING_NOT_RUN",
      "publication_claim_ceiling":"S0",
      "no_mri_rna_tests":True,
      "notes":"Official digital phantom IBSI-1 benchmark is not proof of full IBSI CT/MRI workflow equivalence, and cannot authorize 14-person MRI–RNA associations.",
      "created_utc":datetime.now(timezone.utc).isoformat(),
    }

def offline_test():
    src={"official_source_commit_sha":"abcdef","image_sha256":"aa",
         "mask_sha256":"bb","status":"PASS_OFFICIAL_NIFTI_SOURCE_PROVENANCE"}
    mes={**src,"original_image_roi":{"original_roi_voxels":74},
         "referenced_IBSI_3d_avg":5.32,
         "distinct_IBSI_3d_merge_reference_not_tested":5.12,
         "observed_contrast":5.32,"signed_difference_from_5_32":0,
         "status":"PASS_MATCH_TO_IBSI_3D_AVG_REFERENCE",
         "hcc_14_patient_clinical_eligibility":"NOT_ASSESSED",
         "mri_rna_associations_run":False}
    assert combined(src,mes)["status"]=="PASS_REFERENCE_MATH_AND_SOURCE_COHERENCE"
    mes["observed_contrast"]=4.
    mes["signed_difference_from_5_32"]=-1.32
    mes["status"]="REVIEW_SOFTWARE_REFERENCE_DEVIATION"
    assert combined(src,mes)["status"]=="HOLD_IBSI_IMPLEMENTATION_REFERENCE_DEVIATION_REVIEW"
    mes["image_sha256"]="WRONG"
    try:combined(src,mes)
    except ValueError:pass
    else:raise AssertionError("Tampered source must fail")
    print("HCC_IBSI1_14_PATIENT_MULTISOURCE_GATE_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_ibsi_final")
    a=p.parse_args()
    if a.offline_test:return offline_test()
    report=combined(read(SOURCE),read(MEASURE))
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"hcc_ibsi1_clinical_guard_readiness.json").write_text(
      json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
