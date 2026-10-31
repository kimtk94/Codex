#!/usr/bin/env python3
"""Immutable IBSI1 CT A/B source + measured numerical snapshot/claim regression.

Offline: no CT pixels or patient data downloaded, no external dependencies.
This is NOT rerunning CT features; real calculations are in documented Actions.
"""
import json
import math
from pathlib import Path

FILE=Path("research/hcc/HCC_IBSI_CT_A_B_FROZEN_REFERENCES_20261031.json")
LEDGER=Path("research/hcc/HCC_VERIFICATION_LEDGER.csv")
SRC="6da96021bc91faf4c0cb7fd7fa56a4225d2064a8"
IMG="909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb"
MSK="0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78"
SET={"Mean","Median","InterquartileRange","GLCM_2D_averaged_Contrast",
     "GLCM_2_5D_direction_merged_Contrast"}
EXPECTED={"A":{"status":"PASS_CT_A_FIVE_INDEPENDENT_FOUR_PYRADIOMICS",
               "size":[204,201,60],"roi":114596,"run_id":41186059566,
               "glcm_avg":7.851406512761039,"glcm_2_5":5.960989939109945},
          "B":{"status":"PASS_CT_B_INTERPOLATION_FBN32_FEATURE_REFERENCES",
               "size":[100,99,60],"roi":27359,"run_id":41186558822,
               "glcm_avg":11.884355956323969,"glcm_2_5":8.659118505446799}}

def verify(d):
    if d["source_commit"]!=SRC or d["image_sha256"]!=IMG or d["mask_sha256"]!=MSK:
        raise ValueError("Original official CT source provenance changed")
    if set(d["configs"])!={"A","B"}:
        raise ValueError("Unexpected count of verified CT configurations")
    if d["dataset"]!="IBSI1 CT patient PAT1 NSCLC test phantom; not HCC patient":
        raise ValueError("Reference CT data misrepresented as clinical HCC")
    if d["source_license"]!="CC BY-NC 3.0" or d["original_or_resampled_image_redistributed"]:
        raise ValueError("Source licensing/redistribution problem")
    limits=d["remaining"]
    if (limits["IBSI1_CT_C_D_E"]!="NOT_EXECUTED"
        or limits["IBSI2_FILTERED"]!="NOT_EXECUTED"
        or limits["HCC18"]!="PARTIAL" or limits["HCC20"]!="PENDING"
        or limits["claim_ceiling"]!="S0"
        or limits["clinical_pretreatment_same_lesion"]!="NOT_VERIFIED"):
        raise ValueError("CT phantom does not authorize patient-level inference")
    for name,expected in EXPECTED.items():
        cfg=d["configs"][name]
        if (cfg["status"]!=expected["status"] or cfg["size_xyz"]!=expected["size"]
            or cfg["intensity_roi_voxels"]!=expected["roi"]
            or cfg["run_id"]!=expected["run_id"]):
            raise ValueError("CT original geometry, ROI or frozen run changed")
        if len(cfg["references"])!=5 or {x["feature"] for x in cfg["references"]}!=SET:
            raise ValueError("Missing reference or duplicate CT A/B features")
        for row in cfg["references"]:
            if row["feature"]=="GLCM_2D_averaged_Contrast":
                if row["pyradiomics"] is not None:
                    raise ValueError("PyRadiomics native 2D:avg claim is unsupported")
            elif row["pyradiomics"] is None:
                raise ValueError("Four PyRadiomics measurements missing")
            if (not math.isfinite(row["independent"])
                or row["ibsi_tolerance"] <= 0
                or abs(row["independent"]-row["expected"]) > row["ibsi_tolerance"]):
                raise ValueError("Official IBSI CT ref mismatch")
            if row["pyradiomics"] is not None:
                if (not math.isfinite(row["pyradiomics"])
                    or abs(row["pyradiomics"]-row["expected"])>row["ibsi_tolerance"]):
                    raise ValueError("PyRadiomics reference mismatch")
        m={x["feature"]:x for x in cfg["references"]}
        if (abs(m["GLCM_2D_averaged_Contrast"]["independent"]-expected["glcm_avg"])>1e-8
            or abs(m["GLCM_2_5D_direction_merged_Contrast"]["independent"]-
                   expected["glcm_2_5"])>1e-8
            or abs(m["GLCM_2_5D_direction_merged_Contrast"]["independent"]-
                   m["GLCM_2_5D_direction_merged_Contrast"]["pyradiomics"])>1e-5):
            raise ValueError("Previously measured independent GLCM data drift")
    if d["configs"]["B"]["interpolation"].find("no independent resampler")<0:
        raise ValueError("Shared image interpolation limitation was removed")
    return True

def main():
    d=json.loads(FILE.read_text(encoding="utf-8"))
    verify(d)
    import csv
    with LEDGER.open(encoding="utf-8",newline="") as f:
        by_id={x["id"]:x for x in csv.DictReader(f)}
    if by_id["HCC-18"]["status"]!="PARTIAL" or by_id["HCC-20"]["status"]!="PENDING":
        raise ValueError("Invalid HCC manuscript inference promotion")
    broken=json.loads(json.dumps(d))
    broken["configs"]["B"]["references"][-1]["independent"]=100.
    try:
        verify(broken)
    except ValueError:
        pass
    else:
        raise AssertionError("Tampered B contrast was not rejected")
    broken=json.loads(json.dumps(d))
    broken["remaining"]["HCC20"]="PASS"
    try:
        verify(broken)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid molecular outcome was promoted")
    print("HCC_IBSI_CT_A_B_FROZEN_REFERENCE_AND_CLINICAL_GATES_OFFLINE_PASS")

if __name__=="__main__":
    main()
