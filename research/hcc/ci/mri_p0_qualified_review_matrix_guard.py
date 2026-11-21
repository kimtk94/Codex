#!/usr/bin/env python3
"""Evidence-gated HCC MRI14 anatomical & clinical reviewer matrix verification.

No patient is eligible based on a case ID match, voxel header match, radiomics
ICC or a ChatGPT-generated/CI-generated contact sheet. Expert state transitions
require auditable source evidence and reviewer identity. Never execute RNA tests.
"""
import argparse,csv,copy,datetime,math,re
from pathlib import Path

ROOT=Path("research/hcc")
REVIEW=ROOT/"HCC_MRI14_QUALIFIED_REVIEW_EVIDENCE_MATRIX_20261031.csv"
ROSTER=ROOT/"HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
PHASE=ROOT/"HCC_MRI14_PV_SOURCE_14_CASE_PRIMARY_FEATURE_CHANGE_20261031.csv"
LEDGER=ROOT/"HCC_VERIFICATION_LEDGER.csv"
P0={"TCGA-BC-A10Y","TCGA-DD-A4NH","TCGA-G3-A25T","TCGA-G3-AAV1"}
P1={"TCGA-BC-A3KG","TCGA-BC-A5W4","TCGA-DD-A4NF","TCGA-DD-A4NJ","TCGA-G3-A3CJ"}
P2={"TCGA-BC-A69I","TCGA-G3-A7M7","TCGA-G3-AAV2","TCGA-G3-AAV3","TCGA-G3-AAV7"}
EXPERT_FIELDS=("ART_tumor_ROI_expert","registered_PV_tumor_ROI_expert",
    "independent_nonrigid_registration_approval")
PATIENT_FIELDS=("MRI_pre_HCC_treatment","RNA_same_selected_tumor")
ALL_FIELDS=EXPERT_FIELDS+PATIENT_FIELDS
STATES={"PASS","FAIL","NOT_ASSESSED"}
DEFAULT="NOT_ASSESSED"

def read(path):
    with path.open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def close(x,y,tol=0.000015):
    return math.isfinite(float(x)) and abs(float(x)-float(y)) <= tol

def validate(rows,roster,phase,ledger):
    patients={r["patient_id"]:r for r in roster}
    sources={r["patient_id"]:r for r in phase}
    if len(roster)!=14 or len(phase)!=14 or len(rows)!=14:
        raise ValueError("FROZEN_14_PATIENT_COUNT_DRIFT")
    if len(patients)!=14 or len(sources)!=14 or set(patients)!=set(sources):
        raise ValueError("DUPLICATE_OR_MISSING_SOURCE_ID")
    ids=[x["patient_id"] for x in rows]
    if set(ids)!=set(patients) or len(set(ids))!=14:
        raise ValueError("REVIEWER_CASE_SOURCE_ID_MISMATCH")
    if {r["patient_id"] for r in rows if r["clinical_evidence_priority"]=="P0"}!=P0:
        raise ValueError("HCC_TREATMENT_PRIORITY_P0_DRIFT")
    if {r["patient_id"] for r in rows if r["clinical_evidence_priority"]=="P1"}!=P1:
        raise ValueError("REVIEW_PRIORITY_P1_DRIFT")
    if {r["patient_id"] for r in rows if r["clinical_evidence_priority"]=="P2"}!=P2:
        raise ValueError("REVIEW_PRIORITY_P2_DRIFT")
    accepted=[]
    for x in rows:
        pid=x["patient_id"]
        a,b=patients[pid],sources[pid]
        if int(x["selected_tumor_number"])!=int(a["representative_tumor_number"]):
            raise ValueError("EXPERT_REVIEW_INDEX_TUMOR_WAS_CHANGED")
        if not close(x["frozen_r1_tumor_volume_ml"],a["representative_volume_ml"]):
            raise ValueError("SOURCE_TUMOR_VOLUME_DRIFT")
        if not close(x["frozen_r1_r2_dice"],a["rater1_vs_rater2_dice"]):
            raise ValueError("SOURCE_READER_DICE_DRIFT")
        if not close(x["raw_vs_registered_glcm_contrast_signed_pct"],b["glcm_contrast_signed_pct"]):
            raise ValueError("UNLOCKED_GLCM_SOURCE_SENSITIVITY")
        file=f"{pid}_tumor{x['selected_tumor_number']}_ART_vs_registeredPV_rater_masks.png"
        if x["png_contact_sheet_filename"]!=file or x["git_actions_artifact_id"]!="13042520765":
            raise ValueError("CONTACT_SHEET_IMAGE_SOURCE_PROVENANCE_MISMATCH")
        if x["source_space_orientation"]!="PASS_HEADER_GEOMETRY_ONLY":
            raise ValueError("UNAPPROVED_GEOMETRY_VERDICT")
        if any(x[y] not in STATES for y in ALL_FIELDS):
            raise ValueError("UNKNOWN_EXPERT_OR_PATIENT_STATUS")
        progress=any(x[y]!=DEFAULT for y in ALL_FIELDS)
        eligible=x["qualified_patient_eligible"]
        if eligible not in STATES:
            raise ValueError("UNKNOWN_CLINICAL_ELIGIBILITY_STATUS")
        if progress or eligible!=DEFAULT:
            if not x["reviewer_reference"].strip() or not x["reviewer_name"].strip():
                raise ValueError("EXPERT_STATUS_WITHOUT_REVIEWER_AND_EVIDENCE")
            try:
                datetime.date.fromisoformat(x["review_date"])
            except ValueError:
                raise ValueError("EXPERT_STATUS_WITHOUT_VALID_REVIEW_DATE")
            if not re.search(r"https?://|doi:|GDC:|TCIA:",x["reviewer_reference"]):
                raise ValueError("EVIDENCE_REFERENCE_NOT_TRACEABLE")
        complete=all(x[y]=="PASS" for y in ALL_FIELDS)
        if eligible=="PASS" and not complete:
            raise ValueError("PATIENT_ELIGIBILITY_WITH_MISSING_EVIDENCE")
        if eligible=="FAIL" and not any(x[y]=="FAIL" for y in ALL_FIELDS):
            raise ValueError("EXCLUSION_WITHOUT_DOCUMENTED_FAIL")
        if eligible=="PASS":
            accepted.append(pid)
    records={r["id"]:r for r in ledger}
    if records["HCC-20"]["status"]!="PENDING" or records["HCC-20"]["claim_ceiling"]!="S0":
        raise ValueError("MRI_RNA_STATISTICAL_CLAIM_PREMATURELY_PROMOTED")
    if records["HCC-17"]["status"]!="PENDING" or records["HCC-17"]["claim_ceiling"]!="S0":
        raise ValueError("CLINICAL_ELIGIBILITY_LEDGER_NOT_REVIEWED")
    # Even a fully documented eligible case is not authorization to run
    # the 12 prespecified tests; researcher must separately approve that gate.
    return {"case_count":len(rows),"P0":4,"P1":5,"P2":5,
            "qualified_cases_documented":len(accepted),
            "qualified_pair_analysis_approved":False,
            "MRI_RNA_12_tests_executed":0,
            "publication_claim_ceiling":"S0"}

def negative_tests(rows,roster,phase,ledger):
    def expect_rejected(change):
        r=copy.deepcopy(rows)
        change(r[0])
        try:validate(r,roster,phase,ledger)
        except (ValueError,KeyError):return
        raise AssertionError("MISSING_FAIL_CLOSED_EXPERT_GATE")
    expect_rejected(lambda x:x.update({"qualified_patient_eligible":"PASS"}))
    expect_rejected(lambda x:x.update({"ART_tumor_ROI_expert":"PASS"}))
    expect_rejected(lambda x:x.update({"clinical_evidence_priority":"P2"}))
    expect_rejected(lambda x:x.update({"selected_tumor_number":"1" if x["patient_id"]=="TCGA-BC-A10Y" else "3"}))
    expect_rejected(lambda x:x.update({"raw_vs_registered_glcm_contrast_signed_pct":"0"}))
    print("HCC_MRI14_QUALIFIED_REVIEW_NEGATIVE_CI_GUARD_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--negative-tests",action="store_true")
    args=ap.parse_args()
    rows,roster,phase,ledger=map(read,[REVIEW,ROSTER,PHASE,LEDGER])
    result=validate(rows,roster,phase,ledger)
    if args.negative_tests:negative_tests(rows,roster,phase,ledger)
    print("HCC_MRI14_QUALIFIED_REVIEW_EVIDENCE_MATRIX_HOLD_PASS",result)

if __name__=="__main__":main()
