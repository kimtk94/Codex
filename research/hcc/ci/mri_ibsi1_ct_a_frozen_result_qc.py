#!/usr/bin/env python3
"""Immutable source-locked IBSI1 CT-A validation snapshot: lightweight CI guard.

This is an archival regression: the original CT measurement was actually
executed in GitHub Actions 41186059566. Do not construe this offline
snapshot as fresh PyRadiomics extraction or overall IBSI certification.
"""
import csv
import json
import math
from pathlib import Path

BASE = Path("research/hcc")
SNAPSHOT = BASE / "HCC_IBSI1_CT_CONFIG_A_OFFICIAL_BENCHMARK_20261031.json"
LEDGER = BASE / "HCC_VERIFICATION_LEDGER.csv"
CASES = BASE / "HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
EXPECTED = {
    "Mean": ("Q4LE", 13.4, 1.1, 13.408426123075849, 13.408426123075849),
    "Median": ("Y12H", 46., 0.3, 46., 46.),
    "InterquartileRange": ("SALO", 56., 0.5, 56., 56.),
    "GLCM_2D_averaged_Contrast": ("ACUI", 7.85, 0.26, 7.851406512761039, None),
    "GLCM_2_5D_direction_merged_Contrast":
        ("ACUI", 5.96, 0.27, 5.960989939109945, 5.96098993910995),
}
SOURCE_COMMIT = "6da96021bc91faf4c0cb7fd7fa56a4225d2064a8"
IMG_SHA = "909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb"
MASK_SHA = "0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78"
RUN = "https://github.com/kimtk94/Codex/actions/runs/41186059566"

def near(actual, expected, err=1e-9):
    return isinstance(actual, (int, float)) and math.isfinite(actual) and abs(actual-expected) < err

def check(snapshot, ledger, patients):
    if (snapshot["id"] != "HCC_IBSI1_CT_CONFIG_A_V1"
        or snapshot["source"]["repo"] != "theibsi/data_sets"
        or snapshot["source"]["commit"] != SOURCE_COMMIT
        or snapshot["source"]["image_sha256"] != IMG_SHA
        or snapshot["source"]["mask_sha256"] != MASK_SHA
        or snapshot["source"]["image_shape_xyz"] != [204,201,60]
        or snapshot["source"]["morphological_roi_voxels"] != 125256
        or snapshot["source"]["intensity_roi_voxels"] != 114596
        or snapshot["source"]["license"] != "CC BY-NC 3.0"
        or snapshot["run"] != RUN):
        raise ValueError("Frozen actual CT-A original input or run provenance drift")
    p = snapshot["preprocessing"]
    if (p["rounding"] != "nearest_integer" or p["interpolation"] != "none"
        or p["hu_interval"] != [-500,400] or p["binWidth_hu"] != 25
        or p["in_plane_direction_count"] != 4 or p["GLCM_symmetric"] is not True):
        raise ValueError("CT-A source-aware preprocessing signature changed")
    rows = snapshot["official_reference"]
    if len(rows) != 5 or set(r["feature"] for r in rows) != set(EXPECTED):
        raise ValueError("Incomplete or duplicate official CT-A reference family")
    for r in rows:
        code, ref, tol, independent, py = EXPECTED[r["feature"]]
        if r["code"] != code or not near(r["reference"],ref) or not near(r["tolerance"],tol):
            raise ValueError("Unreviewed IBSI reference or tolerance drift")
        if not near(r["independent"],independent,1e-9):
            raise ValueError("Verified independent source measurement changed")
        if py is None:
            if r["pyradiomics"] is not None:
                raise ValueError("PyRadiomics falsely claimed unsupported 2D:avg")
        elif not near(r["pyradiomics"],py,1e-9):
            raise ValueError("Verified PyRadiomics source measurement changed")
        if abs(r["independent"]-ref) > tol:
            raise ValueError("Verified independent value exceeds IBSI tolerance")
        if py is not None and abs(r["pyradiomics"]-ref) > tol:
            raise ValueError("Verified PyRadiomics value exceeds IBSI tolerance")
    if (not near(snapshot["cross_impl_2_5D_absolute_difference"],5.329070518200751e-15)
        or snapshot["integrator_status"] != "PASS_CT_A_FIVE_INDEPENDENT_FOUR_PYRADIOMICS"
        or snapshot["ct_B_E"] != "NOT_EXECUTED"
        or snapshot["ibsi2_filtered_maps"] != "NOT_EXECUTED"
        or snapshot["hcc18"] != "PARTIAL" or snapshot["hcc20"] != "PENDING"
        or snapshot["claim_ceiling"] != "S0"):
        raise ValueError("Unverified claim promotion or missing CT A evidence")
    status = {r["id"]:r["status"] for r in ledger}
    if (status.get("HCC-13") != "PARTIAL"
        or status.get("HCC-18") != "PARTIAL"
        or status.get("HCC-20") != "PENDING"):
        raise ValueError("Frozen benchmark must not authorize clinical eligibility")
    if len(patients) != 14 or len({r["patient_id"] for r in patients}) != 14:
        raise ValueError("Frozen MRI technical candidate count drift")
    h18 = next(r for r in ledger if r["id"] == "HCC-18")
    if RUN not in h18["evidence_url"] and RUN not in h18["observed"]:
        raise ValueError("HCC-18 ledger does not record actual CT-A evidence")
    return True

def main():
    data = json.loads(SNAPSHOT.read_text(encoding="utf8"))
    with LEDGER.open(newline="",encoding="utf8") as f:
        ledger = list(csv.DictReader(f))
    with CASES.open(newline="",encoding="utf8") as f:
        patients = list(csv.DictReader(f))
    check(data, ledger, patients)
    mutated = json.loads(json.dumps(data))
    mutated["official_reference"][3]["pyradiomics"] = 7.851406512761039
    try: check(mutated,ledger,patients)
    except ValueError: pass
    else: raise AssertionError("Incorrect PyRadiomics 2D avg claim went undetected")
    mutated = json.loads(json.dumps(data))
    mutated["ct_B_E"] = "PASS"
    try: check(mutated,ledger,patients)
    except ValueError: pass
    else: raise AssertionError("False unexecuted CT B–E promotion not rejected")
    mutated = json.loads(json.dumps(data))
    mutated["official_reference"][4]["independent"] = 10
    try: check(mutated,ledger,patients)
    except ValueError: pass
    else: raise AssertionError("Tampered source measurement not rejected")
    print("HCC_IBSI_CT_A_SOURCE_LOCKED_5_PLUS_4_AND_CLINICAL_GUARDS_PASS")

if __name__=="__main__":
    main()
