#!/usr/bin/env python3
"""Read-only HCC MRI14 GDC-relative treatment/source lineage crosswalk.

Clinical observations only. Never compare TCIA shifted DICOM date to GDC
relative treatment/specimen days; never promote case-level barcode similarity
to lesion-specific MRI-RNA eligibility or run biological associations.
"""
import argparse,csv,io,json,datetime,copy
from collections import Counter,defaultdict
from pathlib import Path

DIR=Path("research/hcc")
CLIN=DIR/"HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv"
EVENTS=DIR/"HCC_MRI_10_DATED_YES_TREATMENTS_SOURCE_20261031.csv"
RNA=DIR/"HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv"
REVIEW=DIR/"HCC_MRI14_QUALIFIED_REVIEW_EVIDENCE_MATRIX_20261031.csv"
INDEX=DIR/"HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
P0={"TCGA-BC-A10Y","TCGA-DD-A4NH","TCGA-G3-A25T","TCGA-G3-AAV1"}
P1={"TCGA-BC-A3KG","TCGA-BC-A5W4","TCGA-DD-A4NF","TCGA-DD-A4NJ","TCGA-G3-A3CJ"}
P2={"TCGA-BC-A69I","TCGA-G3-A7M7","TCGA-G3-AAV2","TCGA-G3-AAV3","TCGA-G3-AAV7"}
FIELDS=[
    "patient_id","clinical_evidence_priority","MRI_index_tumor",
    "RNA_aliquot_barcode","GDC_STAR_file_UUID",
    "GDC_relative_RNA_tissue_collection_day","diagnosis_prior_treatment_values",
    "GDC_count_reported_yes","GDC_number_dated_yes_before_tissue",
    "HCC_context_dated_yes_rows","HCC_context_distinct_treatment_days",
    "HCC_context_earliest_treatment_day","GDC_HCC_earliest_treatment_to_tissue_interval_days",
    "non_HCC_dated_yes_rows","dated_yes_event_uuids","source_treatment_context",
    "TCIA_baseline_pre_surgical_collection_level_statement",
    "source_MRI_scan_id_to_GDC_tissue_episode","specific_MRI_pre_HCC_treatment",
    "same_MRI_index_lesion_to_RNA_aliquot","qualified_image_reader_approval",
    "eligible_radiogenomics","case_level_decision","evidence_action"
]

def load(path):
    with path.open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def unique(rows):
    found={}
    for r in rows:
        k=r["patient_id"]
        if k in found:
            raise ValueError("DUPLICATE_CASE_IN_REFERENCE:"+k)
        found[k]=r
    return found

def classify_event(r):
    hcc="hepatocellular carcinoma" in r["primary_diagnosis"].casefold()
    # Treat absence of a liver site as HCC DIAGNOSIS context only, not
    # confirmed treatment of the index tumor.
    extra=set(v.strip().casefold() for v in r["treatment_anatomic_sites"].split("|") if v.strip())
    if hcc and ("cecum" in extra or "appendix" in extra):
        raise ValueError("CONFLICTING_HCC_DIAGNOSIS_AND_OTHER_ANATOMIC_TREATMENT_SITE")
    return "HCC_DIAGNOSIS_CONTEXT_UNVERIFIED_LESION" if hcc else (
        "DIFFERENT_SITE_CECUM_APPENDIX" if {"cecum","appendix"} & extra else
        "UNSPECIFIED_NON_HCC_DIAGNOSIS")

def evidence(clin,events,rna,review,index):
    c=unique(clin);q=unique(review);n=unique(rna);t=unique(index)
    ids=set(c)
    if len(ids)!=14 or not(ids==set(q)==set(n)==set(t)):
        raise ValueError("FROZEN_14_SOURCE_COHORT_ID_OR_MISSING_RECORD_DRIFT")
    if {p for p in ids if q[p]["clinical_evidence_priority"]=="P0"}!=P0 or \
       {p for p in ids if q[p]["clinical_evidence_priority"]=="P1"}!=P1 or \
       {p for p in ids if q[p]["clinical_evidence_priority"]=="P2"}!=P2:
        raise ValueError("CLINICAL_SOURCE_PRIORITY_CHANGED")
    by=defaultdict(list);uuids=set()
    for e in events:
        pid=e["patient_id"]
        if pid not in ids:
            raise ValueError("UNKNOWN_TREATMENT_CASE_ID")
        eventid=e["treatment_id"]
        if not eventid or eventid in uuids:
            raise ValueError("TREATMENT_UUID_MISSING_OR_DUPLICATED")
        uuids.add(eventid)
        if (e["treatment_start_day"].strip()=="" or
            e["rna_specimen_collection_day"].strip()==""):
            raise ValueError("DATED_EARLY_SOURCE_EVENT_MISSING_DAY")
        treatment=float(e["treatment_start_day"])
        specimen=float(e["rna_specimen_collection_day"])
        if treatment>specimen:
            raise ValueError("SOURCE_EARLY_TREATMENT_OCCURRED_AFTER_TISSUE")
        if abs(specimen-float(c[pid]["sample_days_to_collection"]))>1e-8:
            raise ValueError("GDC_TREATMENT_COLLECTION_DAY_CROSS_SOURCE_MISMATCH")
        by[pid].append((e,classify_event(e),treatment))
    if len(events)!=10 or len(uuids)!=10:
        raise ValueError("TEN_ORIGINAL_DATED_YES_RECORDS_REQUIRED")
    counts=Counter()
    out=[]
    for pid in sorted(ids):
        g=c[pid];v=q[pid];i=t[pid];a=n[pid]
        if g["gdc_primary_tumor_sample_matched"]!="YES":
            raise ValueError("GDC_PRIMARY_TUMOR_SAMPLE_ID_UNVERIFIED")
        if not a["aliquot_barcode"].startswith(pid+"-01"):
            raise ValueError("RNA_ALIQUOT_CASE_OR_PRIMARY_TUMOR_BARCODE_DRIFT")
        if int(i["representative_tumor_number"])!=int(v["selected_tumor_number"]):
            raise ValueError("FROZEN_MRI_LESION_SELECTION_CHANGED")
        if any(v[x]!="NOT_ASSESSED" for x in (
              "MRI_pre_HCC_treatment","RNA_same_selected_tumor",
              "qualified_patient_eligible","ART_tumor_ROI_expert",
              "registered_PV_tumor_ROI_expert")):
            raise ValueError("NO_SOURCE_EVIDENCE_SUPPORTS_CASE_ELIGIBILITY")
        items=by[pid]
        if g["therapy_yes_before_tissue_candidate"]=="YES_REVIEW" and not items:
            raise ValueError("MISSING_POSITIVE_DATED_TREATMENT_EVIDENCE")
        if g["therapy_yes_before_tissue_candidate"]!="YES_REVIEW" and items:
            raise ValueError("FALSE_NEGATIVE_EARLY_TREATMENT_SOURCE_REPORT")
        hcc=[(e,day) for e,kind,day in items if kind.startswith("HCC_DIAGNOSIS")]
        non=[(e,day) for e,kind,day in items if not kind.startswith("HCC_DIAGNOSIS")]
        if pid in P0 and not hcc:
            raise ValueError("HCC_P0_REQUIRES_HCC_CONTEXT_DATED_INTERVENTION")
        if pid not in P0 and hcc:
            raise ValueError("UNEXPECTED_HCC_EARLY_INTERVENTION_OUTSIDE_P0")
        if pid=="TCGA-BC-A5W4" and (len(non)!=1 or
           classify_event(non[0][0])!="DIFFERENT_SITE_CECUM_APPENDIX"):
            raise ValueError("SOURCE_OTHER_ORGAN_TREATMENT_A5W4_MISCLASSIFIED")
        if non and pid!="TCGA-BC-A5W4":
            raise ValueError("UNEXPECTED_DATED_NON_HCC_SITE_ANNOTATION")
        specimen_day=float(g["sample_days_to_collection"])
        min_day=min((d for _,d in hcc),default=None)
        delta=specimen_day-min_day if min_day is not None else None
        if min_day is not None and delta<0:
            raise ValueError("NEGATIVE_INTERVAL_BETWEEN_RECORDED_TREATMENT_TISSUE")
        counts["P"+q[pid]["clinical_evidence_priority"][-1]]+=1
        counts["hcc_dated_events"]+=len(hcc)
        counts["non_HCC_dated_events"]+=len(non)
        counts["patients_with_dated_HCC_context"]+=int(bool(hcc))
        counts["cases_with_prior_report_yes"]+=int(g["therapy_yes_before_tissue_candidate"]=="YES_REVIEW")
        if not items:
            context="NO_DATED_EARLY_YES_SOURCE_EVENTS"
        elif hcc:
            context="HCC_DIAGNOSIS_TREATMENT_DATED_BEFORE_GDC_RNA_TISSUE_NOT_MRI"
        else:
            context="DATED_OTHER_ANATOMIC_SITE_NOT_PROVEN_HCC_TREATMENT"
        r=dict(
            patient_id=pid,clinical_evidence_priority=v["clinical_evidence_priority"],
            MRI_index_tumor=i["representative_tumor_number"],
            RNA_aliquot_barcode=a["aliquot_barcode"],GDC_STAR_file_UUID=a["gdc_file_id"],
            GDC_relative_RNA_tissue_collection_day=g["sample_days_to_collection"],
            diagnosis_prior_treatment_values=g["prior_treatment_values"],
            GDC_count_reported_yes=g["reported_therapy_yes_count"],
            GDC_number_dated_yes_before_tissue=len(items),
            HCC_context_dated_yes_rows=len(hcc),
            HCC_context_distinct_treatment_days=len(set(day for _,day in hcc)),
            HCC_context_earliest_treatment_day="" if min_day is None else f"{min_day:g}",
            GDC_HCC_earliest_treatment_to_tissue_interval_days="" if delta is None else f"{delta:g}",
            non_HCC_dated_yes_rows=len(non),
            dated_yes_event_uuids="|".join(e["treatment_id"] for e,_,_ in items),
            source_treatment_context=context,
            TCIA_baseline_pre_surgical_collection_level_statement="YES_COLLECTION_LEVEL_NOT_PATIENT_PRE_HCC_THERAPY",
            source_MRI_scan_id_to_GDC_tissue_episode="NOT_ASSESSED",
            specific_MRI_pre_HCC_treatment="NOT_ASSESSED",
            same_MRI_index_lesion_to_RNA_aliquot="NOT_ASSESSED",
            qualified_image_reader_approval="NOT_ASSESSED",
            eligible_radiogenomics="NOT_ASSESSED",
            case_level_decision="HOLD_NO_PATIENT_LEVEL_CLINICAL_PROOF",
            evidence_action="OBTAIN_AUTHORIZED_SCAN_TREATMENT_AND_INDEX_TUMOR_TISSUE_LINKAGE" if pid in P0 else
                            "VERIFY_MRI_EPISODE_AND_SAME_LESION_PROVENANCE")
        out.append(r)
    if counts["P0"]!=4 or counts["P1"]!=5 or counts["P2"]!=5:
        raise ValueError("EXPECTED_4_5_5_PRIORITY_SPLIT")
    if (counts["hcc_dated_events"]!=9 or counts["non_HCC_dated_events"]!=1
        or counts["patients_with_dated_HCC_context"]!=4
        or counts["cases_with_prior_report_yes"]!=5):
        raise ValueError("DATED_TREATMENT_SOURCE_CLASSIFICATION_CHANGED")
    assert len(out)==14 and len({x["patient_id"] for x in out})==14
    return out,dict(counts)

def negative_test(clin,events,rna,review,index):
    def bad_change(f):
        a,b,c,d,e=map(copy.deepcopy,(clin,events,rna,review,index))
        f(a,b,c,d,e)
        try:evidence(a,b,c,d,e)
        except ValueError:return
        raise AssertionError("DANGEROUS_SOURCE_CROSSWALK_CHANGE_NOT_REJECTED")
    bad_change(lambda a,b,c,d,e:b[0].update(rna_specimen_collection_day="99"))
    bad_change(lambda a,b,c,d,e:b[0].update(treatment_id=b[1]["treatment_id"]))
    bad_change(lambda a,b,c,d,e:a[0].update(therapy_yes_before_tissue_candidate="UNKNOWN_TIMING_OR_NO_YES"))
    bad_change(lambda a,b,c,d,e:d[0].update(qualified_patient_eligible="PASS"))
    bad_change(lambda a,b,c,d,e:c[0].update(aliquot_barcode="TCGA-ZZ-XXXX-01A-11R-XXXX-07"))
    print("HCC_MRI14_CLINICAL_CROSSWALK_FIVE_NEGATIVE_CONTROLS_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",default="artifacts/hcc_mri14_clinical_crosswalk")
    args=p.parse_args()
    pieces=[load(x) for x in (CLIN,EVENTS,RNA,REVIEW,INDEX)]
    rows,counts=evidence(*pieces)
    if args.offline_test:
        negative_test(*pieces)
        print("HCC_MRI14_CLINICAL_CROSSWALK_OFFLINE_QC_PASS",counts)
        return
    d=Path(args.out_dir);d.mkdir(parents=True,exist_ok=True)
    with (d/"HCC_MRI14_GDC_TREATMENT_TISSUE_SOURCE_TRACEABILITY_20261031.csv").open(
          "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(rows)
    summary=dict(
        status="SOURCE_METADATA_RECONCILIATION_PASS_CLINICAL_ELIGIBILITY_HOLD",
        source_GDC_relative_time_only=True,
        reference="https://www.cancerimagingarchive.net/collection/tcga-lihc/",
        patient_count=14,source_events_dated_yes_before_tissue=10,
        hcc_context_event_rows=9,non_HCC_event_rows=1,
        HCC_early_treatment_patient_count=4,
        other_organ_early_treatment_patient_count=1,
        A5W4_other_organ="Cecum|Appendix",
        A10Y_n_HCC_early_source_rows=6,
        A10Y_n_distinct_HCC_treatment_days=4,
        P0=4,P1=5,P2=5,
        TCIA_baseline_pre_surgical_is_case_level_pretherapy_evidence=False,
        DICOM_dates_safe_to_join_to_GDC_relative_days=False,
        source_MRI_to_GDC_surgical_episode_identified=0,
        expert_same_index_lesion_approved=0,
        qualified_eligible_n="NOT_ASSESSED",
        actual_MRI_RNA_tests=0,claim_ceiling="S0")
    (d/"HCC_MRI14_CLINICAL_SOURCE_RECONCILIATION_SUMMARY_20261031.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary))

if __name__=="__main__":
    main()
