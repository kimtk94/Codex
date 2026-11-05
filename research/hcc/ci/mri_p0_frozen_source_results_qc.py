#!/usr/bin/env python3
"""Outcome-blind regression for frozen HCC MRI registered-PV source QC."""
import argparse
import csv
import hashlib
import io
import math
import zipfile
from pathlib import Path

BASE = Path("research/hcc")
ROOT = "HCC_MRI14_PV_SOURCE_"
EXPECTED = {
    "hcc_mri14_raw_vs_registered_pv_all_features.csv": (
        "89721948d9be9942c25b1be95388c8121eb2b89298443c7e0edf30fd563d0184", 56),
    "hcc_mri14_pv_source_feature_sensitivity.csv": (
        "504615f735d0acb1d301d7de0be6a779c069e3efdddb08c119bebe632cfb00a0", 10),
    "hcc_mri14_pv_source_two_reader_icc_a1.csv": (
        "86c205f0ef719012cb05104a3082209f6c1b852c453dcfa2e405414d44ddfcf0", 20),
    "hcc_mri14_registered_source_reproducibility_summary.json": (
        "a5ab10797db11b592a957f5464b50b2bb767956f316c3e557f0c4da78f904a96", None),
}
LOCKED = {
    "original_firstorder_Entropy": (3.30938, 0.894505, 1, 0, .98903),
    "original_firstorder_InterquartileRange": (2.94410, 0.942857, 4, 0, .99325),
    "original_glcm_Contrast": (22.07991, 0.894505, 11, 9, .95161),
}
PHASES = ("raw_pv", "reoriented_art_pv")

def records(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))

def near(a, b, tol=0.00002):
    return math.isfinite(float(a)) and abs(float(a)-b) <= tol

def audit(archive_path=None):
    cases = records((BASE / "HCC_MRI14_PV_SOURCE_14_CASE_PRIMARY_FEATURE_CHANGE_20261031.csv").read_bytes())
    feats = records((BASE / "HCC_MRI14_PV_SOURCE_10_FEATURE_SENSITIVITY_20261031.csv").read_bytes())
    iccs = records((BASE / "HCC_MRI14_PV_SOURCE_TWO_READER_ICC_20_20261031.csv").read_bytes())
    frozen = records((BASE / "HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv").read_bytes())
    roster = {r["patient_id"] for r in frozen}
    assert len(cases) == 14 and len(roster) == 14
    assert {r["patient_id"] for r in cases} == roster
    assert len(feats) == 10 and len(iccs) == 20
    assert {r["source_run"] for r in cases + feats + iccs} == {"41191599451"}
    assert {r["clinical_eligibility"] for r in cases} == {"NOT_ASSESSED"}
    f_by = {r["feature"]: r for r in feats}
    assert len(f_by) == 10
    for name, (med, rho, n10, n20, reg_icc) in LOCKED.items():
        a = f_by[name]
        assert a["locked_primary"] == "YES"
        assert near(a["median_abs_pct_change"], med)
        assert near(a["patient_mean_rank_rho"], rho)
        assert int(a["cases_abs_pct_ge10"]) == n10
        assert int(a["cases_abs_pct_ge20"]) == n20
        x = [r for r in iccs if r["feature"] == name and r["source_phase"] == PHASES[1]]
        assert len(x) == 1 and near(x[0]["icc_a1"], reg_icc)
    assert sum(r["locked_primary"] == "YES" for r in feats) == 3
    for name in ("VoxelVolume", "SurfaceArea", "Sphericity", "Elongation"):
        f = f_by["original_shape_" + name]
        assert near(f["median_abs_pct_change"], 0)
        assert near(f["max_abs_pct_change"], 0)
        assert near(f["patient_mean_rank_rho"], 1)
    assert len({(r["source_phase"], r["feature"]) for r in iccs}) == 20
    assert len({r["source_phase"] for r in iccs}) == 2
    ledger = {r["id"]: r for r in records((BASE / "HCC_VERIFICATION_LEDGER.csv").read_bytes())}
    for id, status in (("HCC-12", "PARTIAL"), ("HCC-13", "PARTIAL"),
                       ("HCC-14", "PARTIAL"), ("HCC-17", "PENDING"),
                       ("HCC-20", "PENDING")):
        assert ledger[id]["status"] == status and ledger[id]["claim_ceiling"] == "S0"
    sap = (BASE / "HCC_MRI_RNA_SOURCE_PHASE_SAP_ADDENDUM_20261031.md").read_text()
    assert "NOT_EXECUTED" in sap and "12" in sap and "art_pv" in sap

    if archive_path is not None:
        with zipfile.ZipFile(archive_path) as z:
            assert set(z.namelist()) == set(EXPECTED)
            for name, (digest, count) in EXPECTED.items():
                data = z.read(name)
                assert hashlib.sha256(data).hexdigest() == digest, name
                if count is not None:
                    assert len(records(data)) == count, name
            full = records(z.read("hcc_mri14_raw_vs_registered_pv_all_features.csv"))
        keys = {(r["patient_id"], r["rater"], r["phase"]) for r in full}
        assert len(keys) == 56
        assert {r["patient_id"] for r in full} == roster
        assert {r["rater"] for r in full} == {"rater1", "rater2"}
        assert {r["phase"] for r in full} == set(PHASES)
        assert all(r["eligible_for_MRI_RNA"] == "NOT_ASSESSED" and
                   r["research_claim_ceiling"] == "S0" for r in full)
        assert all(len(r["source_sha256"]) == len(r["mask_sha256"]) == 64 for r in full)
        for r in full:
            assert float(r["physical_affine_offset_mm"]) <= 0.5
        # Verify snapshot signed changes from the original per-reader numbers.
        for case in cases:
            sample = [r for r in full if r["patient_id"] == case["patient_id"]]
            for feature, column in (("original_firstorder_Entropy", "entropy_signed_pct"),
                                   ("original_firstorder_InterquartileRange", "iqr_signed_pct"),
                                   ("original_glcm_Contrast", "glcm_contrast_signed_pct")):
                before = sum(float(r[feature]) for r in sample if r["phase"] == PHASES[0]) / 2
                after = sum(float(r[feature]) for r in sample if r["phase"] == PHASES[1]) / 2
                pct = (after - before) / abs(before) * 100
                assert near(pct, float(case[column]), 0.0051), (case["patient_id"], feature)
    print("HCC_P0_SOURCE_14_PATIENT_56_ROW_SNAPSHOT_QC_PASS",
          "archive_checked" if archive_path else "offline")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-zip", type=Path)
    args = parser.parse_args()
    audit(args.evidence_zip)
