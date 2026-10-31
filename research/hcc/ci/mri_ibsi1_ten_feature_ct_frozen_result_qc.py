#!/usr/bin/env python3
"""Offline immutable IBSI1 ten-feature / IBSI1-2 CT source QC for every HCC PR.

Live original phantom feature extraction was verified in run #214.
This reads committed, small, source-derived feature values and geometry
only. Never authorizes HCC MRI-RNA molecular analyses or full IBSI claims.
"""
import argparse,csv,json,math
from pathlib import Path
ROOT=Path("research/hcc")
FEATURES=ROOT/"HCC_IBSI1_TEN_FEATURE_PHANTOM_RESULTS_20261031.csv"
CT=ROOT/"HCC_IBSI_CT_OFFICIAL_SOURCE_MANIFEST_20261031.json"
LEDGER=ROOT/"HCC_VERIFICATION_LEDGER.csv"
CASES=ROOT/"HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
BASE={
 "VoxelVolume":("YEKZ",592.,592.,4.),
 "SurfaceArea":("C0JK",388.,388.0706298811,3.),
 "Sphericity":("QCFX",.843,.8429401437,.005),
 "Elongation":("Q3CK",.816,.8163212281,.005),
 "Mean":("Q4LE",2.15,2.1486486486,.015),
 "Median":("Y12H",1.,1.,.005),
 "Entropy":("TLU2",1.27,1.2656115556,.015),
 "InterquartileRange":("SALO",3.,3.,.005),
 "Contrast":("ACUI",5.32,5.3244799938,.015),
 "JointEntropy":("TU9B",2.4,2.3997112784,.015),
}
CT_IMG="909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb"
CT_MASK="0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78"
SOURCE_COMMIT="6da96021bc91faf4c0cb7fd7fa56a4225d2064a8"

def read_csv(p):
    with p.open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))
def check(rows,ct,ledger,cohort):
    if len(rows)!=10 or len(set(r["feature"] for r in rows))!=10:
        raise ValueError("Missing or duplicate frozen ten IBSI feature rows")
    if set(r["feature"] for r in rows)!=set(BASE):
        raise ValueError("Frozen HCC ten feature family changed")
    for row in rows:
        name=row["feature"];code,expected,measured,tol=BASE[name]
        if row["IBSI_code"]!=code or row["status"]!="PASS":
            raise ValueError("IBSI reference or pass flag changed: "+name)
        if abs(float(row["reference"])-expected)>1e-10 or abs(float(row["measured"])-measured)>1e-8:
            raise ValueError("Previously verified official source feature value drift: "+name)
        diff=abs(float(row["measured"])-float(row["reference"]))
        if (not math.isfinite(diff) or diff>tol
            or abs(diff-float(row["abs_difference"]))>1e-8
            or abs(float(row["local_or_IBSI_tolerance"])-tol)>1e-10):
            raise ValueError("IBSI agreement or tolerance changed: "+name)
    if ct["source_commit"]!=SOURCE_COMMIT:
        raise ValueError("Original official IBSI source commit mismatch")
    if ct["image_sha256"]!=CT_IMG or ct["mask_sha256"]!=CT_MASK:
        raise ValueError("CT source image/mask SHA changed")
    if (ct["image_shape"]!=[204,201,60] or ct["roi_voxels"]!=125256
        or ct["license"]!="CC BY-NC 3.0"
        or ct["original_image_redistributed"] is not False):
        raise ValueError("Original CT geometry or licensing drift")
    if not (ct["ibsi1_ibsi2_images_identical"] and ct["ibsi1_ibsi2_masks_identical"]):
        raise ValueError("IBSI1 and IBSI2 CT source identity changed")
    if ct["ibsi1_CT_A_E_preprocessing"]!="NOT_EXECUTED" or ct["ibsi2_CT_filtered_feature_validation"]!="NOT_EXECUTED":
        raise ValueError("Unrun CT preprocessing/filtered benchmark incorrectly promoted")
    if ct["clinical_HCC_eligibility"]!="NOT_ASSESSED" or ct["mri_rna_tests"]!="NOT_EXECUTED" or ct["claim_level"]!="S0":
        raise ValueError("IBSI CT crosswalk improperly promoted patient data")
    if len(cohort)!=14 or len({r["patient_id"] for r in cohort})!=14:
        raise ValueError("HCC patient denominator changed")
    gates={r["id"]:r["status"] for r in ledger}
    if gates.get("HCC-13")!="PARTIAL" or gates.get("HCC-18")!="PARTIAL" or gates.get("HCC-20")!="PENDING":
        raise ValueError("IBSI reference data cannot approve image clinic or association")
    return True

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--offline-test",action="store_true")
    args=parser.parse_args()
    rows=read_csv(FEATURES)
    ct=json.loads(CT.read_text(encoding="utf-8"))
    ledger=read_csv(LEDGER)
    cohort=read_csv(CASES)
    check(rows,ct,ledger,cohort)
    if args.offline_test:
        altered=[dict(x) for x in rows]
        altered[0]["measured"]="1"
        try:check(altered,ct,ledger,cohort)
        except ValueError:pass
        else:raise AssertionError("Tampered IBSI observed feature not rejected")
        wrong=dict(ct)
        wrong["ibsi1_CT_A_E_preprocessing"]="DONE"
        try:check(rows,wrong,ledger,cohort)
        except ValueError:pass
        else:raise AssertionError("False CT preprocessing promotion not rejected")
    print("HCC_IBSI1_TEN_OF_TEN_AND_IBSI_CT_DUAL_SOURCE_FROZEN_OFFLINE_QC_PASS")

if __name__=="__main__":main()
