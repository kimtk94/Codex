#!/usr/bin/env python3
"""No-network HCC IBSI-1 official original phantom result and scientific claim QC."""
import argparse,hashlib,json,math,csv
from pathlib import Path

FIXED="research/hcc/HCC_IBSI1_OFFICIAL_PHANTOM_GLCM_VALIDATION_20261031.json"
LEDGER="research/hcc/HCC_VERIFICATION_LEDGER.csv"
MANIFEST="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
FACTOR="research/hcc/HCC_MRI_14_GLCM_BINWIDTH_VOXEL_FACTORIAL_20261031.csv"

def audit(data):
    if data["official_repository_commit"]!="6da96021bc91faf4c0cb7fd7fa56a4225d2064a8":
        raise ValueError("IBSI official git source changed")
    if data["image_sha256"]!="83773ac2a288aa93cf819a98eaf301c18d35d5876182ec9c18733184e2b7a83a":
        raise ValueError("IBSI original image source SHA drift")
    if data["mask_sha256"]!="3032d340944b577b83bc559ea7ae9a6034b84633a840eff39570ec17aa1d6281":
        raise ValueError("IBSI original mask source SHA drift")
    if data["volume_shape_xyz"]!=[5,4,4] or data["roi_voxels"]!=74 or data["directions_3d"]!=13:
        raise ValueError("IBSI original phantom geometry or ROI changed")
    observed=data["pyradiomics"]["contrast"]
    reference=data["independent_pure_stdlib"]["contrast_3d_direction_average"]
    merged=data["independent_pure_stdlib"]["contrast_3d_direction_merged"]
    if (not math.isfinite(observed) or abs(observed-reference)>1e-9 or
        abs(reference-5.32)>0.01 or abs(merged-5.12)>0.01):
        raise ValueError("Independent reference and PyRadiomics disagree on original IBSI")
    if data["pyradiomics"]["status"]!="PASS_MATCH_TO_IBSI_3D_AVG_REFERENCE":
        raise ValueError("Official source benchmark not verified")
    if data["full_IBSI_standardization_certification"]!="NOT_CLAIMED":
        raise ValueError("Single phantom must not be claimed to certify full IBSI")
    if (data["mri_rna_biological_associations"]!="NOT_EXECUTED" or
        data["clinical_HCC_14_eligibility"]!="NOT_ASSESSED" or
        data["claim_ceiling"]!="S0"):
        raise ValueError("Source QC improperly promoted clinical inference")
    with open(MANIFEST,encoding="utf-8",newline="") as f:
        cohort=list(csv.DictReader(f))
    with open(FACTOR,encoding="utf-8",newline="") as f:
        factorial=list(csv.DictReader(f))
    with open(LEDGER,encoding="utf-8",newline="") as f:
        ledger={r["id"]:r for r in csv.DictReader(f)}
    if len(cohort)!=14 or len({r["patient_id"] for r in cohort})!=14 or len(factorial)!=24:
        raise ValueError("Frozen 14 HCC cases or 24 factor rows changed")
    if any(ledger[x]["status"]!="PARTIAL" for x in ("HCC-13","HCC-18")) or ledger["HCC-20"]["status"]!="PENDING":
        raise ValueError("IBSI phantom is not authorized to promote HCC gate statuses")
    return True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    data=json.loads(Path(FIXED).read_text(encoding="utf-8"))
    audit(data)
    if a.offline_test:
        modified=json.loads(json.dumps(data))
        modified["full_IBSI_standardization_certification"]="YES"
        try:audit(modified)
        except ValueError:pass
        else:raise AssertionError("False full-IBSI certification was accepted")
        modified=json.loads(json.dumps(data))
        modified["pyradiomics"]["contrast"]=5.12
        try:audit(modified)
        except ValueError:pass
        else:raise AssertionError("3D merged mistaken for direction averaged")
    print("HCC_IBSI1_OFFICIAL_PINNED_3D_AVG_CONTRAST_BENCHMARK_AND_S0_CI_PASS")

if __name__=="__main__":main()
