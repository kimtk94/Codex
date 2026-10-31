#!/usr/bin/env python3
"""HCC Stage34: fail-closed clinical source pairing evidence gates for 14 TCGA-LIHC MRI/RNA candidates.

Source evidence is case and RNA sample lineage, not same index lesion or treatment chronology.
All records are outcome-blind. No GDC shifted DICOM dates are compared with relative days.
Does not produce clinical GO from metadata, does not perform MRI-RNA biological testing.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from mri_p0_clinical_gdc_relative_timeline_crosswalk import (
    CLIN, EVENTS, RNA, REVIEW, INDEX, P0, P1, P2, load, evidence
)

N=14
DIR=Path("research/hcc")
P0_GATE="HCC_CONTEXT_EARLY_SOURCE_TREATMENT_TISSUE_TIMING_REVIEW"
P1_GATE="LONGITUDINAL_OR_OTHER_SITE_SOURCE_RECONCILIATION"
P2_GATE="NO_EARLY_HCC_SOURCE_EVENT_NOT_PROOF_OF_PRETREATMENT"
FIELDS=[
 "patient_id","priority","frozen_index_tumor","source_mri_segment_qc",
 "source_mri_artifact_id","GDC_STAR_file_uuid","GDC_STAR_md5",
 "GDC_primary_tumor_aliquot","RNA_specimen_relative_collection_day",
 "GDC_case_primary_tumor_barcode_link","HCC_context_dated_yes_event_rows",
 "HCC_context_distinct_start_days","HCC_context_earliest_treatment_day",
 "early_other_site_dated_yes_rows","source_treatment_scope",
 "requested_source_treatment_episode_review",
 "MRI_source_StudyInstanceUID","MRI_source_SeriesInstanceUID",
 "MRI_scan_to_GDC_treatment_episode_verified",
 "MRI_before_all_relevant_HCC_therapy_verified",
 "MRI_index_lesion_to_RNA_sample_portion_verified",
 "image_anatomy_expert_review_verified",
 "registered_PV_expert_review_verified",
 "source_evidence_request","clinical_patient_status",
 "fully_eligible_patient","MRI_RNA_biology_tests","claim_ceiling"
]
REQUESTS={
 "P0":"Obtain deidentified scan-to-HCC-treatment episode sequence and authoritative MRI-before-therapy status; verify resection lesion to exact RNA sample portion",
 "P1":"Reconcile discordant/undated treatment episodes or other-organ surgery; request scan episode bridge and exact selected-lesion-to-RNA sample evidence",
 "P2":"Verify baseline MRI preceded ALL relevant HCC therapies; case-level prior_treatment=No and collection-level pre-surgical are insufficient; verify selected lesion to RNA",
}

def require(cond,msg):
    if not cond:
        raise ValueError(msg)

def unique(rows):
    out={}
    for r in rows:
        pid=r["patient_id"]
        require(pid not in out,"DUPLICATE_SOURCE_PATIENT")
        out[pid]=r
    return out

def frozen(rev,clin,rna,idx):
    a,b,c,d=map(unique,(rev,clin,rna,idx))
    require(len(a)==N and set(a)==set(b)==set(c)==set(d),
            "FROZEN_14_CASE_UNIVERSE_MISMATCH")
    for pid in a:
        x=a[pid];y=b[pid];z=c[pid];i=d[pid]
        require(x["source_space_orientation"]=="PASS_HEADER_GEOMETRY_ONLY",
                "MRI_SOURCE_HEADER_QC_DRIFT")
        require(x["overall_case_status"]=="HOLD_MISSING_CLINICAL_EVIDENCE"
                and x["qualified_patient_eligible"]=="NOT_ASSESSED",
                "CLINICALLY_UNSUPPORTED_PATIENT_PROMOTION")
        for k in ("ART_tumor_ROI_expert","registered_PV_tumor_ROI_expert",
                  "independent_nonrigid_registration_approval","MRI_pre_HCC_treatment",
                  "RNA_same_selected_tumor"):
            require(x[k]=="NOT_ASSESSED","UNVERIFIED_CLINICAL_GATE_PROMOTED:"+k)
        require(not x["reviewer_name"] and not x["review_date"] and not x["reviewer_reference"],
                "QUALIFIED_REVIEWER_EVIDENCE_CHANGED_REASSESS_REQUIRED")
        require(y["gdc_primary_tumor_sample_matched"]=="YES"
                and y["mri_to_tissue_pretherapy_temporal_confirmation"]=="NOT_VERIFIED"
                and y["final_radiogenomics_eligibility"]=="NOT_ASSESSED",
                "MRI_RNA_CLINICAL_LINEAGE_GATES_CHANGED")
        require(i["expert_review"]=="NOT_ASSESSED"
                and i["pretreatment_verified"]=="NOT_ASSESSED"
                and i["eligible_radiogenomics"]=="NOT_ASSESSED",
                "FROZEN_MRI_INDEX_UNVERIFIED_FLAG_CHANGED")
        require(int(i["representative_tumor_number"])==int(x["selected_tumor_number"]),
                "SOURCE_MRI_INDEX_CHANGED")
        require(z["aliquot_barcode"].startswith(pid+"-01"),"GDC_RNA_PRIMARY_TUMOR_BARCODE_DRIFT")
        require(bool(re.fullmatch("[0-9a-fA-F]{32}",z["gdc_md5sum"])),
                "GDC_MD5_INVALID")
        require(bool(re.fullmatch("[0-9a-fA-F-]{36}",z["gdc_file_id"])),
                "GDC_FILE_UUID_INVALID")
        require(float(y["sample_days_to_collection"])>=0,
                "GDC_SAMPLE_RELATIVE_DAY_INVALID")
    return a,b,c,d

def build():
    clin,ev,rna,review,idx=[load(p) for p in (CLIN,EVENTS,RNA,REVIEW,INDEX)]
    cross,counts=evidence(clin,ev,rna,review,idx)
    q,c,a,i=frozen(review,clin,rna,idx)
    require(len(cross)==N and len({r["patient_id"] for r in cross})==N,
            "CROSSWALK_HAS_MISSING_PATIENT")
    require(counts["P0"]==4 and counts["P1"]==5 and counts["P2"]==5,
            "CLINICAL_SOURCE_PRIORITY_DISTRIBUTION_DRIFT")
    require(counts["hcc_dated_events"]==9 and counts["non_HCC_dated_events"]==1
            and counts["patients_with_dated_HCC_context"]==4,
            "OTHER_ORGAN_EVENT_WRONGLY_CONSIDERED_HCC")
    result=[]
    for row in cross:
        pid=row["patient_id"]; x=q[pid];y=c[pid];z=a[pid]
        priority=x["clinical_evidence_priority"]
        require(priority in {"P0","P1","P2"},"INVALID_PRIORITY")
        require(row["clinical_evidence_priority"]==priority
                and row["RNA_aliquot_barcode"]==z["aliquot_barcode"]
                and row["GDC_STAR_file_UUID"]==z["gdc_file_id"],
                "MRI_RNA_CASE_EVIDENCE_WRONG_JOIN")
        require(row["source_MRI_scan_id_to_GDC_tissue_episode"]=="NOT_ASSESSED"
                and row["specific_MRI_pre_HCC_treatment"]=="NOT_ASSESSED"
                and row["same_MRI_index_lesion_to_RNA_aliquot"]=="NOT_ASSESSED"
                and row["eligible_radiogenomics"]=="NOT_ASSESSED",
                "SOURCE_GDC_RELATIVE_TIMELINE_FALSLY_PROMOTED")
        hcc=int(row["HCC_context_dated_yes_rows"])
        non=int(row["non_HCC_dated_yes_rows"])
        if priority=="P0":
            require(hcc>0 and non==0 and pid in P0,"EARLY_HCC_CONTEXT_NOT_P0")
            scope=P0_GATE
        elif priority=="P1":
            require(hcc==0 and pid in P1,"NON_HCC_EARLY_RECORD_WRONG_PRIORITY")
            scope=P1_GATE
        else:
            require(hcc==0 and non==0 and pid in P2,"P2_HAS_EARLY_EVENT")
            scope=P2_GATE
        if pid=="TCGA-BC-A5W4":
            require(non==1 and "DIFFERENT_ANATOMIC_SITE" in row["source_treatment_context"],
                    "A5W4_OTHER_ORGAN_EVENT_MISCLASSIFIED")
        else:
            require(non==0,"UNEXPECTED_OTHER_SITE_DATED_EVENT")
        request=REQUESTS[priority]
        result.append({
            "patient_id":pid,
            "priority":priority,
            "frozen_index_tumor":row["MRI_index_tumor"],
            "source_mri_segment_qc":x["source_space_orientation"],
            "source_mri_artifact_id":x["git_actions_artifact_id"],
            "GDC_STAR_file_uuid":z["gdc_file_id"],
            "GDC_STAR_md5":z["gdc_md5sum"],
            "GDC_primary_tumor_aliquot":z["aliquot_barcode"],
            "RNA_specimen_relative_collection_day":y["sample_days_to_collection"],
            "GDC_case_primary_tumor_barcode_link":"PASS_CASE_AND_RNA_PRIMARY_TUMOR_BARCODE_ONLY",
            "HCC_context_dated_yes_event_rows":hcc,
            "HCC_context_distinct_start_days":row["HCC_context_distinct_treatment_days"],
            "HCC_context_earliest_treatment_day":row["HCC_context_earliest_treatment_day"],
            "early_other_site_dated_yes_rows":non,
            "source_treatment_scope":scope,
            "requested_source_treatment_episode_review":request,
            "MRI_source_StudyInstanceUID":"UNVERIFIED_NOT_SUPPLIED_IN_FROZEN_JOIN",
            "MRI_source_SeriesInstanceUID":"UNVERIFIED_NOT_SUPPLIED_IN_FROZEN_JOIN",
            "MRI_scan_to_GDC_treatment_episode_verified":"NOT_ASSESSED",
            "MRI_before_all_relevant_HCC_therapy_verified":"NOT_ASSESSED",
            "MRI_index_lesion_to_RNA_sample_portion_verified":"NOT_ASSESSED",
            "image_anatomy_expert_review_verified":"NOT_ASSESSED",
            "registered_PV_expert_review_verified":"NOT_ASSESSED",
            "source_evidence_request":"SOURCE_CUSTODIAN_EPISODE_BRIDGE_AND_SAMPLE_LESION_MAPPING_REQUIRED",
            "clinical_patient_status":"UNRESOLVED_HOLD_NO_SOURCE_AUTHORIZED_SAME_TUMOR_PRETREATMENT_CHAIN",
            "fully_eligible_patient":"NOT_ASSESSED",
            "MRI_RNA_biology_tests":0,
            "claim_ceiling":"S0",
        })
    require(len(result)==N,"NOT_ALL_CASES_ACCOUNTED_FOR")
    return result,counts

def report(rows,counts):
    bucket=Counter(r["priority"] for r in rows)
    require(bucket==Counter({"P0":4,"P1":5,"P2":5}),"WRONG_14_SOURCE_BUCKETS")
    summary={
        "stage":"HCC_STAGE34_TCGA_LIHC_MRI14_MRNA_CLINICAL_SOURCE_CHAIN",
        "source":"PUBLIC_FROZEN_GDC_TREATMENT_SAMPLE_RNA_AND_LIVERHCCSEG_MRI_QC",
        "source_patient_denominator":N,
        "source_GDC_primary_tumor_barcode_linked":N,
        "source_HCC_context_yes_events_before_RNA_sample":9,
        "source_HCC_context_yes_event_unique_patients":4,
        "other_organ_yes_event_before_RNA_sample":1,
        "other_organ_event_context":"TCGA-BC-A5W4_CECUM_APPENDIX_NOT_HCC_PROOF",
        "source_priority_groups":{"P0":4,"P1":5,"P2":5},
        "MRI_source_scan_UID_to_GDC_episode_proven_n":0,
        "MRI_before_all_HCC_therapy_confirmed_n":0,
        "MRI_index_lesion_to_RNA_sample_portion_confirmed_n":0,
        "independent_radiologist_review_n":0,
        "source_review_pending_n":N,
        "clinically_eligible_n":"NOT_ASSESSED",
        "clinically_excluded_n":"NOT_ASSESSED",
        "MRI_RNA_biological_tests":0,
        "minimum_future_qualified_n_for_original_panel":10,
        "status":"SOURCE_TRACEABILITY_PASS_CLINICAL_PAIRING_HOLD",
        "claim_ceiling":"S0",
        "DICOM_vs_GDC_relative_calendar_subtraction_permitted":False,
        "TCIA_presurgical_collection_statement_proves_case_preHCCtherapy":False,
        "notes":[
          "Case and primary tumor RNA barcodes match 14/14 but physical same index lesion is not demonstrated.",
          "Four HCC-diagnosis-context pre-tissue treatment patients are review flags, not exclusions.",
          "One earlier recorded affirmative surgery belongs to Cecum/Appendix and cannot count as proven liver intervention.",
          "Neither negative prior_treatment fields nor collection-level presurgical imaging prove absence of all earlier HCC therapy.",
          "Anatomy requires independent physician review; chronology and tumor identity require source-custodian evidence.",
          "Do not run 3 MRI x 4 Hallmark tests until prior prespecified clinical cohort qualification and sample flow.",
        ]
    }
    lines=["# HCC Stage 34: clinical MRI/treatment/RNA specimen pairing source evidence audit","",
      "**Result: source-case linkage PASS; clinical same-index-lesion pretreatment pairing HOLD; S0.**","",
      "- 14/14 frozen MRI cases have a GDC primary tumor RNA case/sample barcode and STAR file identity.",
      "- 14/14 still lack a source-authorized MRI-before-HCC-therapy episode bridge and same selected-tumor RNA aliquot/portion chain.",
      "- Original source evidence: 10 dated pre-specimen Yes treatment records: 9 HCC-diagnosis-context rows in 4 patients and 1 other-organ surgery (Cecum/Appendix, TCGA-BC-A5W4).",
      "- Four P0 are NOT excluded; no eligible count can be inferred from metadata.",
      "- GDC relative days vs shifted TCIA DICOM acquisition dates cannot be calendar-subtracted.",
      "- 4 P0 / 5 P1 / 5 P2 request priorities; qualified radiologist review 0/14.",
      "- 12 biological MRI-RNA tests NOT EXECUTED. Claim ceiling S0.","",
      "| Case | Index | Priority | HCC-context Yes rows before tissue | Other-organ Yes | Same lesion/tissue | MRI-before-therapy |",
      "|---|---:|---|---:|---:|---|---|"]
    for r in rows:
        lines.append(f'| {r["patient_id"]} | {r["frozen_index_tumor"]} | {r["priority"]} | {r["HCC_context_dated_yes_event_rows"]} | {r["early_other_site_dated_yes_rows"]} | HOLD | HOLD |')
    lines+=["","## Evidence needed for Stage 35 (source-custodian / qualified expert)",
     "", "1. Native MRI StudyInstanceUID/SeriesInstanceUID for the exact index lesion and a deidentified authoritative relative sequence of scan and each HCC-specific treatment episode.",
     "2. Exact resected/biopsied tumor lesion-to-RNA sample/portion and aliquot barcode provenance, not case ID alone.",
     "3. Independent qualified abdominal radiologist review of original ART/registered PV index lesion anatomy and registration, with reviewer/date/source reference.",
     "4. Formal source-verified case adjudication eligible/excluded/unresolved, with reasons and 14-person flow accounting. Minimum n >=10 required before frozen 12-test panel; absence of evidence is HOLD not exclusion.",
     "","**Do not update biological study eligibility from this source metadata audit.**",""]
    return summary,"\n".join(lines)

def offline():
    # True-data defensive fixture and policy invariants, no artificial patients.
    rows,_=build()
    assert len(rows)==14 and all(r["fully_eligible_patient"]=="NOT_ASSESSED" for r in rows)
    assert set(r["patient_id"] for r in rows if r["HCC_context_dated_yes_event_rows"])==P0
    x=next(r for r in rows if r["patient_id"]=="TCGA-BC-A5W4")
    assert x["early_other_site_dated_yes_rows"]==1 and x["HCC_context_dated_yes_event_rows"]==0
    assert all(r["MRI_index_lesion_to_RNA_sample_portion_verified"]=="NOT_ASSESSED" for r in rows)
    assert all(r["clinical_patient_status"].startswith("UNRESOLVED_HOLD_") for r in rows)
    print("HCC_STAGE34_OFFLINE_TRUE_FROZEN_14_SOURCE_AND_NO_FALSE_CLINICAL_GO_PASS")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--offline-test",action="store_true")
    a.add_argument("--out-dir",default="artifacts/hcc_stage34_clinical_source")
    args=a.parse_args()
    offline()
    if args.offline_test:return
    rows,counts=build()
    summary,md=report(rows,counts)
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/"stage34_mri14_source_chain_gate_matrix.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (out/"stage34_clinical_source_gate_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    (out/"stage34_clinical_source_evidence_request.md").write_text(md,encoding="utf8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf8") as f:f.write(md)
    print("HCC_STAGE34_MRI14_SOURCE_TRACEABILITY_PASS_CLINICAL_PAIRING_HOLD",
          json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
