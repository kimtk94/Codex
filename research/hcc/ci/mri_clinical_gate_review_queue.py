#!/usr/bin/env python3
"""Construct fail-closed patient review queue for HCC MRI-RNA clinical gate.

Does NOT count pending cases as ineligible, assign actual pretreatment labels,
or run image–RNA correlations. 14 patient technical candidates are held until
source-level image/therapy/tissue/lesion evidence and reviewer adjudication.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

SRC="research/hcc/HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv"
ROI="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
OUT=("patient_id","selected_tumor_number","gdc_prior_treatment_values",
     "reported_therapy_yes_start_day","rna_sample_collection_day",
     "therapy_before_tissue_screen","pathology_slide_min_tumor_cells_pct",
     "pathology_slide_min_tumor_nuclei_pct",
     "review_priority","mri_source_dicom_pretherapy_adjudication",
     "mri_roi_anatomical_reader","mri_rna_same_lesion_tissue_review",
     "clinical_eligibility_decision","reviewer","review_date",
     "required_evidence","source_gdc_run_id")

def read(path):
    with open(path,encoding="utf-8",newline="") as h:
        rows=list(csv.DictReader(h))
    ids=[r["patient_id"] for r in rows]
    if len(rows)!=14 or len(set(ids))!=14:
        raise ValueError("Clinical/ROI source must be 14 unique patients")
    return {r["patient_id"]:r for r in rows}

def build(clinical,roi):
    if set(clinical)!=set(roi):
        raise ValueError("Cross-source patient ID mismatch")
    output=[]
    for pid in sorted(clinical):
        c=clinical[pid]; r=roi[pid]
        if (c["gdc_primary_tumor_sample_matched"]!="YES"
            or c["mri_to_tissue_pretherapy_temporal_confirmation"]!="NOT_VERIFIED"
            or c["final_radiogenomics_eligibility"]!="NOT_ASSESSED"):
            raise ValueError("Source unexpectedly asserts qualified patient")
        if r["expert_review"]!="NOT_ASSESSED":
            raise ValueError("ROI expert review source changed unexpectedly")
        category=c["therapy_yes_before_tissue_candidate"]
        if category=="YES_REVIEW":
            priority="P0_POSSIBLE_YES_TREATMENT_BEFORE_TISSUE"
        elif "Yes" in c["prior_treatment_values"]:
            priority="P1_CONFLICTING_PRIOR_TREATMENT_DIAGNOSES"
        elif c["prior_treatment_values"]=="No":
            priority="P2_REPORTED_NO_PRIOR_TREATMENT_BUT_MRI_NOT_DATED"
        else:
            priority="P1_INDETERMINATE_TREATMENT"
        output.append({
            "patient_id":pid,
            "selected_tumor_number":r["representative_tumor_number"],
            "gdc_prior_treatment_values":c["prior_treatment_values"],
            "reported_therapy_yes_start_day":c["earliest_reported_therapy_yes_day"],
            "rna_sample_collection_day":c["sample_days_to_collection"],
            "therapy_before_tissue_screen":category,
            "pathology_slide_min_tumor_cells_pct":c["linked_slide_tumor_cells_min"],
            "pathology_slide_min_tumor_nuclei_pct":c["linked_slide_tumor_nuclei_min"],
            "review_priority":priority,
            "mri_source_dicom_pretherapy_adjudication":"PENDING_SOURCE_EVIDENCE",
            "mri_roi_anatomical_reader":"PENDING_QUALIFIED_READER",
            "mri_rna_same_lesion_tissue_review":"PENDING_SPECIMEN_REVIEW",
            "clinical_eligibility_decision":"HOLD_UNRESOLVED_NOT_EXCLUDED",
            "reviewer":"","review_date":"",
            "required_evidence":"DICOM/TCIA study crosswalk; treatment timeline; expert ROI/source lesion; RNA aliquot pathology slide",
            "source_gdc_run_id":"41089216888",
        })
    return output

def offline_test():
    c=read(SRC);r=read(ROI)
    out=build(c,r)
    counts=Counter(x["review_priority"].split("_")[0] for x in out)
    assert counts=={"P0":5,"P1":4,"P2":5},counts
    assert all(x["clinical_eligibility_decision"]=="HOLD_UNRESOLVED_NOT_EXCLUDED"
               for x in out)
    assert all(x["mri_roi_anatomical_reader"]=="PENDING_QUALIFIED_READER" for x in out)
    bad=dict(c)
    bad[next(iter(bad))]={**bad[next(iter(bad))],"final_radiogenomics_eligibility":"YES"}
    try:build(bad,r)
    except ValueError:pass
    else:raise AssertionError("Clinical eligibility must fail closed")
    print("HCC_14_CLINICAL_REVIEW_QUEUE_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--output",default="artifacts/hcc_clinical_gate_queue")
    args=p.parse_args()
    if args.offline_test:return offline_test()
    out=build(read(SRC),read(ROI))
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    with (root/"hcc_mri_14_clinical_review_queue.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=OUT);w.writeheader();w.writerows(out)
    p=Counter(x["review_priority"] for x in out)
    info={
        "status":"PASS_FAIL_CLOSED_REVIEW_QUEUE_ONLY",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "technical_candidate_count":14,
        "review_priority_counts":dict(p),
        "verified_pretreatment_mri_patient_count":"NOT_ASSESSED",
        "clinically_excluded_patient_count":"NOT_ASSESSED",
        "unresolved_patient_count":14,
        "claimed_eligible_patient_count":"NOT_ASSESSED",
        "MRI_RNA_association_performed":False,
        "claim_ceiling":"S0",
        "note":"These 14 are unresolved, not 14 clinical exclusions and not 14 qualified participants. No patient can be promoted without independent source timeline and expert ROI review.",
    }
    (root/"hcc_mri_14_clinical_review_queue_summary.json").write_text(
        json.dumps(info,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(info,ensure_ascii=False))
if __name__=="__main__":main()
