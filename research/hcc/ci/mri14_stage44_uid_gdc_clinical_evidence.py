#!/usr/bin/env python3
"""HCC Stage44: original Study/Series UID -> MRI index lesion -> GDC RNA &
treatment source evidence crosswalk; independent source-only/clinical gates.

Input evidence fixed to successful Stage38 #41383511403, Stage43 independent
audit #41438155270 and Stage34 source clinical crosswalk in this repository.
Physical image source UID and primary-tumor RNA case barcode matching do NOT
establish the exact same tumor lesion or MRI-before-HCC-therapy. No calendar
arithmetic between TCIA privacy-shifted DICOM dates and GDC relative days.
No Hallmark MRI-RNA tests; clinical patient n stays NOT_ASSESSED.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter,defaultdict
from pathlib import Path
from mri14_stage34_clinical_source_gate import build as stage34_build
from mri_p0_clinical_gdc_relative_timeline_crosswalk import REVIEW

ORIGINAL_SOURCE_STAGE38_RUN=41383511403
ORIGINAL_SOURCE_STAGE43_RUN=41438155270
FREEZE14=14
UID=re.compile(r"(?:[0-9]+[.])+[0-9]+")
MD5=re.compile(r"[0-9a-f]{32}",re.I)

COLS=(
 "patient_id","clinical_evidence_priority","frozen_MRI_index_tumor",
 "source_DICOM_StudyInstanceUID","source_DICOM_SeriesInstanceUID",
 "source_DICOM_series_description","original_DICOM_source_directory",
 "source_native_PV_NIfTI_sha256","source_PV_image_technical_3d_proven",
 "source_DICOM_CRC_verified_instances","source_fullres_min_pixel_Pearson",
 "source_DICOM_LPS_NIfTI_RAS_max_error_mm",
 "GDC_STAR_RNA_file_UUID","GDC_STAR_RNA_md5",
 "GDC_primary_tumor_RNA_aliquot_barcode",
 "GDC_RNA_tissue_collection_relative_day",
 "GDC_primary_tumor_same_TCGA_case_barcode",
 "frozen_rater1_rater2_tumor_dice",
 "MRI_expert_review_artifact_ID","MRI_index_anatomy_expert_review",
 "MRI_registered_PV_expert_review",
 "HCC_context_Yes_treatment_before_RNA_tissue_rows",
 "HCC_context_distinct_treatment_days",
 "HCC_context_earliest_treatment_relative_day",
 "non_HCC_context_Yes_treatment_before_RNA_tissue_rows",
 "GDC_treatment_source_context",
 "verified_original_MRI_scan_to_GDC_HCC_treatment_episode",
 "verified_original_MRI_before_ALL_relevant_HCC_treatments",
 "verified_same_index_MRI_tumor_as_GDC_RNA_aliquot",
 "clinical_eligible_n_status","research_patient_status",
 "source_required_to_unblock_treatment","source_required_to_unblock_tumor_RNA",
 "source_required_to_unblock_expert",
 "source_image_uid_evidence_run",
 "source_RNA_treatment_evidence_stage",
 "DICOM_shifted_vs_GDC_relative_calendar_subtraction_allowed",
 "MRI_RNA_biological_tests","claim_ceiling"
)
GAPS=(
 "patient_id","priority","index_tumor","source_StudyInstanceUID",
 "source_SeriesInstanceUID","RNA_aliquot_barcode",
 "review_priority_reason","HCC_context_treatment_rows",
 "other_organ_treatment_rows",
 "missing_treatment_episode_evidence","missing_same_tumor_RNA_evidence",
 "missing_radiologist_evidence","clinical_patient_status",
 "research_implication"
)
RATER=(
 "patient_id","index_tumor","source_StudyInstanceUID",
 "source_SeriesInstanceUID","original_scan_source_3d_pass",
 "independent_radiologist_name","review_date_ISO8601",
 "review_qualification","original_MRI_index_tumor_anatomy_result",
 "registered_PV_lesion_anatomy_result",
 "registration_acceptance_result",
 "review_provenance_uri_or_signed_document",
 "scan_before_HCC_treatment_evidence_uri",
 "index_lesion_to_RNA_aliquot_source_evidence_uri",
 "clinical_eligibility_decision","eligibility_decision_reference"
)

def require(ok,reason):
    if not ok:raise ValueError(reason)

def loadcsv(path):
    with Path(path).open(newline="",encoding="utf8") as f:
        return list(csv.DictReader(f))

def unique(items,label):
    out={}
    for v in items:
        k=v["patient_id"]
        require(k not in out,"DUPLICATE_"+label+":"+k)
        out[k]=v
    return out

def source_files(source43,source38):
    c=unique(loadcsv(source43),"STAGE43_SOURCE_CASE")
    h=loadcsv(source38)
    require(len(c)==FREEZE14 and len(h)==247,"PINNED_SOURCE_ARTIFACT_POPULATION_MISMATCH")
    require(len({(r["patient_id"],r["source_directory"]) for r in h})==247,
            "SOURCE_STUDY_SERIES_DIRECTORY_DUPLICATION")
    require(len({r["patient_id"] for r in h})==FREEZE14,"STAGE38_CASE_COVERAGE_NOT14")
    require(all(v["technical_source_PV_3d_match"]=="PASS" and
                v["clinical_eligible"]=="NOT_ASSESSED" and
                v["MRI_before_HCC_therapy"]=="NOT_ASSESSED" and
                v["exact_MRI_index_lesion_GDC_RNA_aliquot"]=="NOT_ASSESSED" and
                str(v["MRI_RNA_tests"])=="0" and v["claim_ceiling"]=="S0"
                for v in c.values()),"STAGE43_UNSUPPORTED_CLINICAL_PROOF_OR_MRI_SOURCE_DRIFT")
    by=defaultdict(list)
    for r in h:
        require(r["status"].startswith("PASS_") and
                r["candidate_is_original_selected_PV"]=="NOT_ASSESSED" and
                r["clinical_eligibility"]=="NOT_ASSESSED",
                "STAGE38_UNVERIFIED_PV_SOURCE_LABEL_PROMOTION")
        by[(r["patient_id"],r["SeriesInstanceUID"])].append(r)
    chosen={}
    for pid,v in c.items():
        suid=v["source_dicom_series_uid"]
        matches=by[(pid,suid)]
        require(len(matches)==1,"SOURCE_SELECTED_SERIES_NOT_UNIQUE_IN_247:"+pid)
        hrow=matches[0]
        study=hrow["StudyInstanceUID"]
        require(bool(UID.fullmatch(study)) and len(study)<=64 and
                bool(UID.fullmatch(suid)) and len(suid)<=64,
                "SOURCE_STUDY_OR_SERIES_UID_INVALID:"+pid)
        require(len(v["source_nifti_sha256"])==64 and
                int(v["DICOM_crc_verified_unique_slices"])>0 and
                float(v["fullres_min_pixel_pearson"])>.9999 and
                float(v["max_DICOM_LPS_to_NIfTI_RAS_error_mm"])<2.0,
                "SOURCE_ORIGINAL_3D_PROVENANCE_NOT_SATISFIED:"+pid)
        chosen[pid]=(v,hrow)
    return chosen

def join(source43,source38):
    src=source_files(source43,source38)
    older,counts=stage34_build()
    clinical=unique(older,"STAGE34_CLINICAL_CASE")
    reviews=unique(loadcsv(REVIEW),"FROZEN_RATER_CLINICAL_REVIEW")
    require(set(reviews)==set(clinical),"FROZEN_14_RATER_REVIEW_ROSTER_MISMATCH")
    require(set(src)==set(clinical) and len(clinical)==FREEZE14,
            "MRI_DICOM_GDC_RNA_14_CASE_PATIENT_JOIN_MISMATCH")
    require(counts["P0"]==4 and counts["P1"]==5 and counts["P2"]==5,
            "STAGE34_PRIORITIZATION_DRIFT")
    require(counts["hcc_dated_events"]==9 and
            counts["non_HCC_dated_events"]==1 and
            counts["patients_with_dated_HCC_context"]==4,
            "ORIGINAL_GDC_TREATMENT_CONTEXT_DRIFT")
    output=[]
    gaps=[]
    rater=[]
    for pid in sorted(src):
        source,header=src[pid]
        c=clinical[pid]
        require(pid==c["patient_id"] and c["GDC_primary_tumor_aliquot"].startswith(pid+"-01") and
                bool(MD5.fullmatch(c["GDC_STAR_md5"])),
                "GDC_CASE_RNA_PRIMARY_TUMOR_BARCODE_NOT_PROVEN:"+pid)
        require(c["MRI_before_all_relevant_HCC_therapy_verified"]=="NOT_ASSESSED"
                and c["MRI_index_lesion_to_RNA_sample_portion_verified"]=="NOT_ASSESSED"
                and c["image_anatomy_expert_review_verified"]=="NOT_ASSESSED"
                and c["fully_eligible_patient"]=="NOT_ASSESSED"
                and c["MRI_RNA_biology_tests"]==0 and c["claim_ceiling"]=="S0",
                "STAGE34_CLINICAL_EVIDENCE_WAS_UNEXPECTEDLY_APPROVED:"+pid)
        hcc=int(c["HCC_context_dated_yes_event_rows"])
        non=int(c["early_other_site_dated_yes_rows"])
        if pid=="TCGA-BC-A5W4":
            require(non==1 and hcc==0 and
                    c["source_treatment_scope"]=="LONGITUDINAL_OR_OTHER_SITE_SOURCE_RECONCILIATION",
                    "OTHER_ORGAN_CECUM_APPENDIX_NOT_HCC_IN_REVIEW_QUEUE")
        else:
            require(non==0,"OTHER_ORGAN_SURGERY_WRONGLY_ATTRIBUTED_TO_HCC")
        study=header["StudyInstanceUID"];series=source["source_dicom_series_uid"]
        priority=c["priority"]
        need_treatment=("P0_SOURCE_HCC_CONTEXT_TREATMENT_TO_SCAN_EPISODE_BRIDGE" if priority=="P0" else
                       "P1_DISCORDANT_OR_OTHER_SITE_TREATMENT_EPISODE_BRIDGE" if priority=="P1" else
                       "P2_NEGATIVE_PRIOR_TREATMENT_NOT_SUFFICIENT_PROVE_ALL_HCC_EPISODES")
        need_tumor="ORIGINAL_INDEX_MRI_LESION_TO_RESECTION_BLOCK_PORTION_RNA_ALIQUOT_CHAIN"
        need_expert="INDEPENDENT_ABDOMINAL_RADIOLOGIST_NATIVE_ART_PV_INDEX_TUMOR_AND_REGISTRATION"
        row={
           "patient_id":pid,
           "clinical_evidence_priority":priority,
           "frozen_MRI_index_tumor":c["frozen_index_tumor"],
           "source_DICOM_StudyInstanceUID":study,
           "source_DICOM_SeriesInstanceUID":series,
           "source_DICOM_series_description":header["SeriesDescription"],
           "original_DICOM_source_directory":header["source_directory"],
           "source_native_PV_NIfTI_sha256":source["source_nifti_sha256"],
           "source_PV_image_technical_3d_proven":"PASS_1095_TOTAL_SLICES_ALL14_TECHNICAL",
           "source_DICOM_CRC_verified_instances":source["DICOM_crc_verified_unique_slices"],
           "source_fullres_min_pixel_Pearson":source["fullres_min_pixel_pearson"],
           "source_DICOM_LPS_NIfTI_RAS_max_error_mm":source["max_DICOM_LPS_to_NIfTI_RAS_error_mm"],
           "GDC_STAR_RNA_file_UUID":c["GDC_STAR_file_uuid"],
           "GDC_STAR_RNA_md5":c["GDC_STAR_md5"],
           "GDC_primary_tumor_RNA_aliquot_barcode":c["GDC_primary_tumor_aliquot"],
           "GDC_RNA_tissue_collection_relative_day":c["RNA_specimen_relative_collection_day"],
           "GDC_primary_tumor_same_TCGA_case_barcode":"PASS_CASE_LEVEL_ONLY",
           "frozen_rater1_rater2_tumor_dice":reviews[pid]["frozen_r1_r2_dice"],
           "MRI_expert_review_artifact_ID":c["source_mri_artifact_id"],
           "MRI_index_anatomy_expert_review":"NOT_ASSESSED",
           "MRI_registered_PV_expert_review":"NOT_ASSESSED",
           "HCC_context_Yes_treatment_before_RNA_tissue_rows":hcc,
           "HCC_context_distinct_treatment_days":c["HCC_context_distinct_start_days"],
           "HCC_context_earliest_treatment_relative_day":c["HCC_context_earliest_treatment_day"],
           "non_HCC_context_Yes_treatment_before_RNA_tissue_rows":non,
           "GDC_treatment_source_context":c["source_treatment_scope"],
           "verified_original_MRI_scan_to_GDC_HCC_treatment_episode":"NOT_ASSESSED",
           "verified_original_MRI_before_ALL_relevant_HCC_treatments":"NOT_ASSESSED",
           "verified_same_index_MRI_tumor_as_GDC_RNA_aliquot":"NOT_ASSESSED",
           "clinical_eligible_n_status":"NOT_ASSESSED",
           "research_patient_status":"HOLD_NO_SCAN_TREATMENT_AND_TUMOR_SPECIMEN_SOURCE_PROOF",
           "source_required_to_unblock_treatment":need_treatment,
           "source_required_to_unblock_tumor_RNA":need_tumor,
           "source_required_to_unblock_expert":need_expert,
           "source_image_uid_evidence_run":ORIGINAL_SOURCE_STAGE43_RUN,
           "source_RNA_treatment_evidence_stage":"STAGE34_FROZEN_GDC_SOURCE",
           "DICOM_shifted_vs_GDC_relative_calendar_subtraction_allowed":"NO",
           "MRI_RNA_biological_tests":0,
           "claim_ceiling":"S0"}
        require(set(row)==set(COLS),"STAGE44_OUTPUT_FIELD_SET_CHANGED")
        output.append(row)
        gaps.append({
          "patient_id":pid,"priority":priority,"index_tumor":c["frozen_index_tumor"],
          "source_StudyInstanceUID":study,"source_SeriesInstanceUID":series,
          "RNA_aliquot_barcode":c["GDC_primary_tumor_aliquot"],
          "review_priority_reason":c["source_treatment_scope"],
          "HCC_context_treatment_rows":hcc,
          "other_organ_treatment_rows":non,
          "missing_treatment_episode_evidence":need_treatment,
          "missing_same_tumor_RNA_evidence":need_tumor,
          "missing_radiologist_evidence":need_expert,
          "clinical_patient_status":row["research_patient_status"],
          "research_implication":"MRI_RNA_ASSOCIATION_STOP_UNTIL_QUALIFIED_SOURCE_PROVEN"})
        rater.append({
          "patient_id":pid,"index_tumor":c["frozen_index_tumor"],
          "source_StudyInstanceUID":study,"source_SeriesInstanceUID":series,
          "original_scan_source_3d_pass":"YES",
          "independent_radiologist_name":"",
          "review_date_ISO8601":"",
          "review_qualification":"",
          "original_MRI_index_tumor_anatomy_result":"NOT_ASSESSED",
          "registered_PV_lesion_anatomy_result":"NOT_ASSESSED",
          "registration_acceptance_result":"NOT_ASSESSED",
          "review_provenance_uri_or_signed_document":"",
          "scan_before_HCC_treatment_evidence_uri":"",
          "index_lesion_to_RNA_aliquot_source_evidence_uri":"",
          "clinical_eligibility_decision":"NOT_ASSESSED",
          "eligibility_decision_reference":""})
    require(len(output)==FREEZE14 and len(gaps)==FREEZE14 and len(rater)==FREEZE14,
            "STAGE44_PATIENT_NOT_ACCOUNTED_FOR")
    summary={
      "stage":"HCC_STAGE44_ORIGINAL_DICOM_UID_TO_GDC_RNA_TREATMENT_CLINICAL_EVIDENCE_MATRIX",
      "frozen_patient_count":14,
      "original_native_PV_to_source_DICOM_full3d_technical_verified":14,
      "original_StudyUID_matched_to_verified_SeriesUID":14,
      "GDC_primary_tumor_case_barcode_sample_linked":14,
      "source_image_slices_fullres_verified":sum(int(r["source_DICOM_CRC_verified_instances"]) for r in output),
      "clinical_evidence_priority":{"P0":4,"P1":5,"P2":5},
      "GDC_HCC_diagnosis_context_dated_Yes_event_rows":9,
      "GDC_HCC_diagnosis_context_patients":4,
      "GDC_dated_other_organ_surgical_event_rows":1,
      "source_MRI_before_relevant_HCC_treatment_verified_n":0,
      "source_MRI_index_lesion_to_GDC_RNA_aliquot_verified_n":0,
      "independent_radiologist_approved_n":0,
      "clinical_eligible_n":"NOT_ASSESSED",
      "clinical_excluded_n":"NOT_ASSESSED",
      "MRI_RNA_biology_tests":0,
      "claim_ceiling":"S0",
      "source_uid_evidence_run_id":ORIGINAL_SOURCE_STAGE43_RUN,
      "source_original_dicom_header_run_id":ORIGINAL_SOURCE_STAGE38_RUN,
      "TCIA_DICOM_shifted_vs_GDC_relative_calendar_subtraction_allowed":False,
      "P0_treatment_source_flags_not_exclusion_count":4,
      "other_organ_surgery_TCGA_BC_A5W4_not_HCC_therapy_proof":True,
      "decision":"IMAGING_SOURCE_UID_PLUS_GDC_CASE_RNA_TECHNICAL_JOIN_PASS_CLINICAL_PAIRING_HOLD"}
    require(summary["source_image_slices_fullres_verified"]==1095,
            "STAGE43_TOTAL_ORIGINAL_SLICE_PROVENANCE_CHANGED")
    return output,gaps,rater,summary

def write_csv(path,fields,data):
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="raise");w.writeheader();w.writerows(data)

def save(dir,output,gaps,rater,s):
    dir.mkdir(parents=True,exist_ok=True)
    write_csv(dir/"stage44_original_MRI_UID_GDC_RNA_treatment_14patient_evidence.csv",COLS,output)
    write_csv(dir/"stage44_14patient_clinical_source_gaps_priority.csv",GAPS,gaps)
    write_csv(dir/"stage44_independent_radiology_source_review_template.csv",RATER,rater)
    (dir/"stage44_original_MRI_GDC_clinical_source_summary.json").write_text(
        json.dumps(s,indent=2)+"\n",encoding="utf8")
    lines=["# HCC Stage44 original MRI DICOM source UID → GDC case/RNA/treatment audit",
      "","Original MRI DICOM→PV NIfTI 14/14 full3D source proven (1095 original slices).",
      "Original MRI StudyInstanceUID matched to original 14 unique SeriesInstanceUIDs.",
      "Primary tumor RNA GDC aliquot and STAR file **same case only**, NOT same index lesion.",
      "HCC-context pre-tissue treatment: 9 dated Yes events across 4 flagged P0 patients.",
      "Other organ surgery TCGA-BC-A5W4 (Cecum/Appendix) NOT HCC treatment evidence.",
      "TCIA shifted source DICOM acquisition dates NOT directly comparable to GDC relative collection/treatment dates.",
      "**Clinically eligible n NOT_ASSESSED, independent radiology 0/14, pretreatment 0/14 proven, same index-lesion RNA 0/14 proven, MRI-RNA 0/12, S0.**",
      "","| Patient | Priority | Index | HCC-context Yes | Other-site Yes | MRI Study UID prefix | Required evidence |",
      "|---|---|---:|---:|---:|---|---|"]
    for r in output:
        lines.append("| "+r["patient_id"]+" | "+r["clinical_evidence_priority"]+" | "+
                     r["frozen_MRI_index_tumor"]+" | "+
                     str(r["HCC_context_Yes_treatment_before_RNA_tissue_rows"])+" | "+
                     str(r["non_HCC_context_Yes_treatment_before_RNA_tissue_rows"])+" | "+
                     r["source_DICOM_StudyInstanceUID"][:22]+"… | "+
                     r["source_required_to_unblock_treatment"]+" |")
    report="\n".join(lines)+"\n"
    (dir/"stage44_MRI_UID_GDC_case_specimen_treatment_evidence_report.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE44_FROZEN_14_UID_TO_GDC_SOURCE_CROSSWALK",
          json.dumps(s,sort_keys=True),flush=True)

def negative_fixtures():
    # Synthetic source rows only; never counted as patient evidence.
    h=[{"patient_id":"TCGA-AA-TEST","SeriesInstanceUID":"1.2.3",
        "StudyInstanceUID":"1.2.4"}]
    assert len({x["SeriesInstanceUID"] for x in h})==1
    require(len({x["patient_id"] for x in h})==1,"INVALID_NEGATIVE_FIXTURE")
    assert not UID.fullmatch("MRI_STUDY_UNKNOWN")
    assert UID.fullmatch("1.2.840.113619")
    assert not MD5.fullmatch("not-a-GDC-md5")
    b,c=stage34_build()
    require(len(b)==14 and c["P0"]==4 and c["P1"]==5 and c["P2"]==5,
            "STAGE34_SOURCE_14_PRIORITY_DRIFT")
    p=next(r for r in b if r["patient_id"]=="TCGA-BC-A5W4")
    require(p["HCC_context_dated_yes_event_rows"]==0 and
            p["early_other_site_dated_yes_rows"]==1,
            "STAGE44_OTHER_ORGAN_NON_HCC_FIXTURE_FAIL")
    require(all(r["fully_eligible_patient"]=="NOT_ASSESSED" for r in b),
            "STAGE44_NO_PREAPPROVED_CASES")
    print("HCC_STAGE44_NEGATIVE_FIXTURES_SOURCE_UID_RNA_TREATMENT_CLINICAL_FAIL_CLOSED_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-stage43-csv",type=Path)
    p.add_argument("--source-stage38-csv",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage44_clinical_source"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    negative_fixtures()
    if a.offline_test:return
    require(a.source_stage43_csv and a.source_stage38_csv and
            a.source_stage43_csv.is_file() and a.source_stage38_csv.is_file(),
            "STAGE44_PINNED_ORIGINAL_SOURCE_UID_AND_HEADER_ARTIFACTS_REQUIRED")
    save(a.out_dir,*join(a.source_stage43_csv,a.source_stage38_csv))
if __name__=="__main__":
    main()
