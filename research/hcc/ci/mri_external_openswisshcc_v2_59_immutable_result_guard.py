#!/usr/bin/env python3
"""Fail-closed reproducible n=59 independent OpenSwissHCC v2 source result audit.

Compares compact permanent 59 patient + 24 bootstrap estimate CSVs against
the exact immutable original 16/16-pass action #41221356861 artifact #13050138178,
with SHA256 checks for seven original source members. No external imaging
data fetch, no clinical/biology inference and no results selection.
"""
import argparse,csv,hashlib,io,json,math,statistics,zipfile
from collections import Counter
from pathlib import Path

ROOT=Path("research/hcc")
COMPACT_PATIENTS=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_INDEX_PATIENT_GLCM_NATIVE3MM_FROZEN_20261101.csv"
COMPACT_STATS=ROOT/"HCC_EXTERNAL_OPENSWISSHCC_V2_59_24_CONDITION_BOOTSTRAP_FROZEN_20261101.csv"
SOURCE_MEMBERS={
 "external_openswisshcc_glcm_native_vs_3mm_same_image.png":
 "daaab625034796ada7a8c54efcb53533365544cd48919fcda858bfae30e3d383",
 "external_venous_24_feature_condition_patient_bootstrap_ci.csv":
 "6399e5ffaadcb16d4da0132fe67c7b2b045a34c370738408c2df0a8a97f27568",
 "external_openswisshcc_venous_glcm_ranked_source_sensitivity.png":
 "edc738684407d0cca761d2ebb11164b7c785063fc259f22c321c978b9e25b793",
 "external_venous_59_primary_6_condition_4_feature_extraction.csv":
 "65a9cbaad86ac7eca2ad9f772d3fa7f64de981349ac678187fcf76bb1b216986",
 "external_venous_59_primary_patient_source_profiles.csv":
 "50de8bbaa897f99aa8b2bc9b7a0cd7d972b820e5cfaa9af4399adee4b964dba6",
 "external_venous_59_primary_source_technical_summary.json":
 "c29e84857f08f2f03de587e282ff664b43a75a66efba338406d8817fd010f7af",
 "external_venous_59_source_case_level_HOLD.csv":
 "fea31c8e37c2b4837ac9789d8b5cb915c207d1ad0fa6751b9ce16ea6e7543a2c",
}
FROZEN_FEATURES={
 "original_glcm_Contrast","original_glcm_JointEntropy",
 "original_firstorder_Entropy","original_firstorder_InterquartileRange"}
PARAMS={("native",12.5),("native",25.),("native",50.),
        ("3mm",12.5),("3mm",25.),("3mm",50.)}
BOOT=4000
SEED=20261101

def read_csv(buf):
    return list(csv.DictReader(io.StringIO(buf.decode("utf8"))))
def comparable(a,b,tol=1.6e-6):
    try:
        a,b=float(a),float(b)
        return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol
    except (ValueError,TypeError):return False

def freeze():
    p=read_csv(COMPACT_PATIENTS.read_bytes())
    s=read_csv(COMPACT_STATS.read_bytes())
    if len(p)!=59 or len({x["subject"] for x in p})!=59:
        raise ValueError("FROZEN_59_INDEPENDENT_SUBJECTS_REQUIRED")
    if len(s)!=24 or len({(x["feature"],x["grid"],float(x["binWidth"])) for x in s})!=24:
        raise ValueError("FROZEN_24_FEATURE_CONDITIONS_UNIQUE_REQUIRED")
    if {(x["feature"],x["grid"],float(x["binWidth"])) for x in s}!={
        (feat,grid,bw) for feat in FROZEN_FEATURES for grid,bw in PARAMS}:
        raise ValueError("FROZEN_4x6_REG_PV_PARAMETER_FAMILY_CHANGED")
    if any(x["claim_ceiling"]!="S0" or x["original_source_run"]!="41221356861"
           or not x["selected_HCC_lesion"].startswith("L")
           or int(x["source_mask_voxels"])<50
           for x in p):
        raise ValueError("ORIGINAL_VENOUS_HCC_PATIENT_PROVENANCE_CHANGED")
    if any(x["claim_ceiling"]!="S0" or x["source_run"]!="41221356861"
           or x["independent_n"]!="59" or x["bootstrap_iterations"]!="4000"
           or not float(x["bootstrap95_low"])<=float(x["median_abs_pct"])<=float(x["bootstrap95_high"])
           for x in s):
        raise ValueError("FROZEN_BOOTSTRAP_CI_OR_BIOLOGY_CEILING_CHANGED")
    if not comparable(statistics.median(float(x["signed_change_pct"]) for x in p),64.635863):
        raise ValueError("FROZEN_59_SOURCE_PATIENT_MEDIAN_REFERENCE_DRIFT")
    if not comparable(next(x["median_abs_pct"] for x in s
           if x["feature"]=="original_glcm_Contrast" and x["grid"]=="3mm" and x["binWidth"]=="25"),
           64.635863):
        raise ValueError("FROZEN_SOURCE_3MM_GLCM_CONTRAST_PRIMARY_REFERENCE_CHANGED")
    return p,s

def validate_artifact(source_zip,compact_p,compact_s):
    with zipfile.ZipFile(source_zip) as z:
        if set(z.namelist())!=set(SOURCE_MEMBERS):
            raise ValueError("EXTERNAL_N59_SOURCE_ORIGINAL_ARTIFACT_MEMBERS_CHANGED")
        chunks={n:z.read(n) for n in SOURCE_MEMBERS}
    for n,h in SOURCE_MEMBERS.items():
        if hashlib.sha256(chunks[n]).hexdigest()!=h:
            raise ValueError("SOURCE_ARTIFACT_16_JOB_SHA256_DRIFT:"+n)
    source=read_csv(chunks["external_venous_59_primary_patient_source_profiles.csv"])
    conditions=read_csv(chunks["external_venous_24_feature_condition_patient_bootstrap_ci.csv"])
    summaries=json.loads(chunks["external_venous_59_primary_source_technical_summary.json"])
    extracted=read_csv(chunks["external_venous_59_primary_6_condition_4_feature_extraction.csv"])
    holds=read_csv(chunks["external_venous_59_source_case_level_HOLD.csv"])
    if (len(source)!=59 or len(extracted)!=354 or len(holds)!=0
        or len(conditions)!=24 or summaries["succeeded_source_matched_venous_n"]!=59
        or summaries["HOLD_source_geometry_or_extraction_n"]!=0
        or summaries["feature_condition_statistics"]!=24
        or summaries["MRI_RNA_12_tests"]!="NOT_EXECUTED"
        or summaries["qualified_image_anatomy_review"]!="NOT_ASSESSED"
        or summaries["claim_ceiling"]!="S0"):
        raise ValueError("SOURCE_N59_EVIDENCE_OR_CLINICAL_LIMITS_CHANGED")
    p={r["subject"]:r for r in compact_p}
    for row in source:
        sid=row["patient_id"]
        a=p.get(sid)
        if a is None or a["selected_HCC_lesion"]!=row["selected_lesion"]:
            raise ValueError("ORIGINAL_SOURCE_PATIENT_OR_INDEX_LESION_CHANGED")
        if (int(a["source_mask_voxels"])!=int(row["mask_voxels"])
            or a["claim_ceiling"]!="S0"
            or any(not comparable(x,y) for x,y in zip(
               a["source_voxel_spacing_xyz_mm"].split("|"),
               row["source_spacing_mm"].split(";")))):
            raise ValueError("ORIGINAL_MANUAL_HCC_ROI_OR_SPACING_DRIFT:"+sid)
        for old,new in (
          ("original_native25_GLCM_Contrast","baseline_native_bw25_glcm_contrast"),
          ("resampled_3mm25_GLCM_Contrast","resampled_3mm_bw25_glcm_contrast"),
          ("signed_change_pct","signed_glcm_3mm_bw25_pct")):
            if not comparable(a[old],row[new]):
                raise ValueError("ORIGINAL_PATIENT_GLCM_MEASUREMENT_DRIFT:"+sid+":"+old)
    if len(p)!=len(source):raise ValueError("PATIENT_ID_UNIVERSE_MISMATCH")
    compact_keys={(r["feature"],r["grid"],float(r["binWidth"])):r for r in compact_s}
    for row in conditions:
        key=(row["feature"],row["grid"],float(row["binWidth"]))
        orig=compact_keys.get(key)
        if orig is None:raise ValueError("MISSING_SOURCE_PARAMETER_ROW")
        for old,new in (
           ("median_abs_pct","median_abs_pct"),
           ("bootstrap95_low","median_abs_pct_bootstrap95_low"),
           ("bootstrap95_high","median_abs_pct_bootstrap95_high"),
           ("patient_spearman_rho","patient_rank_spearman")):
            if not comparable(orig[old],row[new]):
                raise ValueError("ORIGINAL_PARAMETER_BOOTSTRAP_REFERENCE_CHANGED:"+repr(key)+":"+old)
        if (row["independent_technical_subjects"]!="59"
             or row["bootstrap_resamples"]!="4000"
             or row["bootstrap_seed"]!="20261101"
             or row["MRI_RNA_tests_executed"]!="NO"
             or row["no_hypothesis_p_value"]!="YES"):
            raise ValueError("BIOLOGICAL_CLAIM_OR_SAMPLE_UNIT_DRIFT")
    return summaries

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--original-source-zip",type=Path)
    args=ap.parse_args()
    p,s=freeze()
    if not args.original_source_zip:
        print("HCC_OPENSWISS_N59_PERMANENT_RESULT_59_SOURCE_24_BOOTSTRAP_FROZEN_PASS")
        return
    meta=validate_artifact(args.original_source_zip,p,s)
    print("HCC_OPENSWISS_N59_ORIGINAL_7_SHA_354_FEATURE_ROWS_59_PATIENTS_24_CONDITIONS_4000_BOOTSTRAP_PASS",meta["glcm_3mm25"])
if __name__=="__main__":main()
