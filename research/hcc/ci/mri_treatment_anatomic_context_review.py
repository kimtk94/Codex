#!/usr/bin/env python3
"""Distinguish HCC-diagnosis-context treatment from nonliver-site records.

This is a stricter REVIEW QUEUE, not a patient eligibility/exclusion classifier.
An affirmative GDC treatment in the same case is not evidence the selected
MRI lesion underwent that treatment or that the image was acquired afterward.
"""
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

SOURCE="research/hcc/HCC_MRI_10_DATED_YES_TREATMENTS_SOURCE_20261031.csv"
CASES="research/hcc/HCC_MRI_14_GDC_CLINICAL_TREATMENT_GATE_20261031.csv"
OUT=("patient_id","dated_yes_records_before_tissue",
     "hcc_diagnosis_context_dated_yes_records","different_anatomic_site_records",
     "unknown_diagnosis_site_records","priority_original","priority_refined",
     "dated_record_context","unverified_treatment_day_references",
     "tumor_mri_before_treatment","tissue_is_same_mri_hcc_lesion",
     "clinical_eligibility","clinical_reviewer_required")


def read(path):
    with Path(path).open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))


def context(row):
    dx=str(row["primary_diagnosis"]).lower()
    site=str(row["treatment_anatomic_sites"]).lower()
    other_site=any(x in site for x in ("cecum","appendix"))
    if other_site:
        return "OTHER_ANATOMIC_SITE_CECUM_APPENDIX"
    if "hepatocellular carcinoma" in dx:
        return "HCC_DIAGNOSIS_LINKED_ANATOMIC_SITE_NOT_PROVEN"
    return "UNKNOWN_TUMOR_SITE"


def reconcile(treatments, cases):
    if len(treatments)!=10 or len({t["treatment_id"] for t in treatments})!=10:
        raise ValueError("Exactly ten original unique early Yes treatment records required")
    patients={r["patient_id"]:r for r in cases}
    if len(patients)!=14 or len(cases)!=14:
        raise ValueError("14 candidate cases expected")
    by_id=defaultdict(list)
    for t in treatments:
        pid=t["patient_id"]
        if pid not in patients:raise ValueError("Treatment for unexpected patient")
        begin=float(t["treatment_start_day"])
        tissue=float(t["rna_specimen_collection_day"])
        if begin>tissue:raise ValueError("Treatment source row not dated <= tissue day")
        if str(patients[pid]["sample_days_to_collection"]) not in (
            str(tissue),str(int(tissue)),str(tissue)+".0"):
            raise ValueError("Treatment/tissue day source drift")
        by_id[pid].append(t)
    result=[]
    for pid,case in sorted(patients.items()):
        subset=by_id.get(pid,[])
        categories=Counter(context(x) for x in subset)
        n_hcc=categories["HCC_DIAGNOSIS_LINKED_ANATOMIC_SITE_NOT_PROVEN"]
        n_other=categories["OTHER_ANATOMIC_SITE_CECUM_APPENDIX"]
        n_ambig=categories["UNKNOWN_TUMOR_SITE"]
        if n_hcc:
            rank="P0_HCC_DIAGNOSIS_CONTEXT_TREATMENT_REVIEW"
        elif n_other:
            rank="P1_OTHER_ANATOMIC_SITE_DATED_TREATMENT_REVIEW"
        elif "Yes" in case["prior_treatment_values"]:
            rank="P1_CONFLICTING_DIAGNOSIS_TREATMENT"
        else:
            rank="P2_UNVERIFIED_MRI_PRETREATMENT"
        result.append({
          "patient_id":pid,
          "dated_yes_records_before_tissue":len(subset),
          "hcc_diagnosis_context_dated_yes_records":n_hcc,
          "different_anatomic_site_records":n_other,
          "unknown_diagnosis_site_records":n_ambig,
          "priority_original":case["therapy_yes_before_tissue_candidate"],
          "priority_refined":rank,
          "dated_record_context":"|".join(
              sorted({x["treatment_type"]+" ["+context(x)+"] day "+x["treatment_start_day"]
                      for x in subset})),
          "unverified_treatment_day_references":
              "YES" if int(case["reported_therapy_yes_count"])>len(subset) else "NO",
          "tumor_mri_before_treatment":"NOT_VERIFIED",
          "tissue_is_same_mri_hcc_lesion":"NOT_VERIFIED",
          "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
          "clinical_reviewer_required":"YES"
        })
    counts=Counter(x["priority_refined"].split("_")[0] for x in result)
    if counts!=Counter({"P0":4,"P1":5,"P2":5}):
        raise ValueError("Frozen source review priority changed unexpectedly: "+str(counts))
    if set(by_id)!={"TCGA-BC-A10Y","TCGA-BC-A5W4","TCGA-DD-A4NH",
                     "TCGA-G3-A25T","TCGA-G3-AAV1"}:
        raise ValueError("Frozen dated treatment patients changed")
    if [x for x in result if x["patient_id"]=="TCGA-BC-A5W4"][0]["priority_refined"]!="P1_OTHER_ANATOMIC_SITE_DATED_TREATMENT_REVIEW":
        raise ValueError("Non-liver surgery incorrectly classified as HCC")
    return result,counts


def offline_test():
    rows,counts=reconcile(read(SOURCE),read(CASES))
    assert len(rows)==14 and counts=={"P0":4,"P1":5,"P2":5}
    assert all(x["clinical_eligibility"]=="HOLD_UNRESOLVED_NOT_EXCLUDED" for x in rows)
    assert sum(int(x["hcc_diagnosis_context_dated_yes_records"]) for x in rows)==9
    assert sum(int(x["different_anatomic_site_records"]) for x in rows)==1
    assert all(x["tumor_mri_before_treatment"]=="NOT_VERIFIED" for x in rows)
    print("HCC_14_TREATMENT_ANATOMIC_CONTEXT_FAIL_CLOSED_OFFLINE_PASS")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--output",default="artifacts/hcc_refined_treatment")
    args=p.parse_args()
    if args.offline_test:return offline_test()
    rows,counts=reconcile(read(SOURCE),read(CASES))
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    with (out/"hcc_mri14_treatment_site_refined_review_queue.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=OUT)
        w.writeheader();w.writerows(rows)
    report={
        "status":"PASS_DIAGNOSIS_ANATOMY_CONTEXT_REVIEW_ONLY",
        "original_dated_yes_treatment_patients":5,
        "hcc_diagnosis_context_dated_yes_treatment_patients":4,
        "other_site_record_only_dated_yes_treatment_patients":1,
        "other_site_patient":"TCGA-BC-A5W4",
        "other_site_treatment_anatomy":"Cecum|Appendix",
        "n_unique_dated_yes_source_treatment_records":10,
        "review_priority_counts":dict(counts),
        "all_14_patients_hold":True,
        "mri_before_treatment_verified":0,
        "clinical_eligibility":"NOT_ASSESSED",
        "mri_rna_associations_performed":False,
        "claim_level":"S0",
        "caution":"HCC diagnosis context is not proven same tumor lesion or therapy site. Different-site surgery does not prove this case never received HCC treatment."
    }
    (out/"hcc_mri14_treatment_site_refined_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":
    main()
