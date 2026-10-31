#!/usr/bin/env python3
"""HCC TCGA-LIHC 14-case source record adjudication: GDC therapy and ABSOLUTE quality.

Read-only public, checksum-pinned ABSOLUTE; independent GDC cases metadata.
Retain only patient/diagnosis/treatment and selected DNA purity-call metadata.
No patient is marked eligible or excluded; MRI dates and lesion tissue identity
cannot be reconstructed from GDC-relative dates.
"""
import argparse,csv,hashlib,io,json,math,urllib.parse,urllib.request
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from mri_pancan_absolute_purity_audit import fetch_bytes as fetch_absolute
from mri_gdc_clinical_eligibility_prescreen import inputs
from mri_gdc_clinical_eligibility_prescreen import maybe_float

GDC="https://api.gdc.cancer.gov/cases"
FIELDS="submitter_id,project.project_id,diagnoses.diagnosis_id,diagnoses.submitter_id,diagnoses.prior_treatment,diagnoses.days_to_diagnosis,diagnoses.primary_diagnosis,diagnoses.diagnosis_is_primary_disease,diagnoses.treatments.treatment_id,diagnoses.treatments.submitter_id,diagnoses.treatments.treatment_or_therapy,diagnoses.treatments.treatment_type,diagnoses.treatments.days_to_treatment_start,diagnoses.treatments.days_to_treatment_end,diagnoses.treatments.pretreatment,diagnoses.treatments.treatment_anatomic_sites,diagnoses.treatments.treatment_intent_type,samples.submitter_id,samples.sample_type,samples.days_to_collection"
SOURCE_FILE="research/hcc/HCC_MRI_14_PANCAN_ABSOLUTE_PURITY_PROXY_20261031.csv"
P0_IDS=("TCGA-BC-A10Y","TCGA-BC-A5W4","TCGA-DD-A4NH",
        "TCGA-G3-A25T","TCGA-G3-AAV1")
RECORD_FIELDS=("patient_id","diagnosis_id","diagnosis_barcode",
  "prior_treatment","diagnosis_day","primary_diagnosis",
  "treatment_id","treatment_submitter_id","treatment_or_therapy",
  "treatment_type","treatment_intent_type","treatment_anatomic_sites",
  "pretreatment_field","treatment_start_day","treatment_end_day",
  "rna_specimen_collection_day","relative_treatment_vs_tissue",
  "mri_before_treatment","interpretation")
SUMMARY_FIELDS=("patient_id","rna_specimen_collection_day",
 "reported_prior_treatment_values","reported_yes_treatment_records",
 "yes_treatment_known_day_count","yes_therapy_start_on_or_before_tissue_count",
 "yes_therapy_start_after_tissue_count","yes_therapy_unknown_day_count",
 "diagnoses_with_yes_treatment","absolute_dna_source_sample",
 "absolute_call_status","absolute_solution","absolute_purity",
 "absolute_ploidy","absolute_call_row_count",
 "priority","clinical_eligibility","source_limitation")


def get_source_cases(patients):
    filt={"op":"and","content":[
      {"op":"in","content":{"field":"submitter_id","value":patients}},
      {"op":"in","content":{"field":"project.project_id","value":["TCGA-LIHC"]}}
    ]}
    query=urllib.parse.urlencode({"filters":json.dumps(filt,separators=(",",":")),
        "fields":FIELDS,"size":100,"format":"JSON"})
    req=urllib.request.Request(GDC+"?"+query,headers={
      "User-Agent":"HCC-14-Clinical-Treatment-Record-Source-QC/1.0",
      "Accept-Encoding":"identity"})
    with urllib.request.urlopen(req,timeout=65) as r:
        payload=r.read(5_000_001)
    if len(payload)>5_000_000:raise ValueError("Oversized GDC cases source")
    result=json.loads(payload)
    data=result.get("data") or {}
    hits=data.get("hits")
    if not isinstance(hits,list) or len(hits)!=14:
        raise ValueError("Incomplete source GDC case records")
    if {h["submitter_id"] for h in hits}!=set(patients):
        raise ValueError("GDC cases are not the frozen 14")
    return {h["submitter_id"]:h for h in hits}


def load_purity_calls(raw,specimen_map):
    """Parse exact sample column, not regex hits across multiple columns.

    The ABSOLUTE file is a source of algorithmic estimates; a 'called' status
    still cannot be elevated to RNA-aliquot purity or clinical eligibility.
    """
    rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")),delimiter="\t"))
    if not rows:raise ValueError("ABSOLUTE source empty")
    required={"sample","call status","purity","ploidy","solution","array"}
    if not required.issubset(rows[0]):
        raise ValueError("ABSOLUTE source schema missing: "+str(required-set(rows[0])))
    result={}
    for patient,specimen in specimen_map.items():
        found=[x for x in rows if str(x.get("sample") or "").upper()[:16]==specimen]
        if len(found)>1:
            # Never silently pick one solution if original study has multiple
            # rows or solutions for a sample. Preserve all for review.
            unique={tuple(str(x.get(k) or "") for k in
                     ("sample","purity","ploidy","call status","solution"))
                    for x in found}
            if len(unique)>1:status="MULTIPLE_DISTINCT_ABSOLUTE_SOLUTIONS_REVIEW"
            else:status="DUPLICATE_IDENTICAL_SOURCE_ROWS_REVIEW"
        elif len(found)==1:
            status="ONE_SPECIMEN_SOURCE_ROW"
        else:
            status="NO_ABSOLUTE_SPECIMEN_ROW"
        result[patient]={
            "count":len(found),"status":status,
            "samples":sorted(set(str(x["sample"]) for x in found)),
            "call_status":sorted(set(str(x.get("call status") or "") for x in found)),
            "solution":sorted(set(str(x.get("solution") or "") for x in found)),
            "purity":sorted(set(str(x.get("purity") or "") for x in found)),
            "ploidy":sorted(set(str(x.get("ploidy") or "") for x in found)),
        }
    return result


def flatten(case, pid, aliquot, abs_call):
    sample_id=aliquot[:16]
    samples=[s for s in (case.get("samples") or [])
             if str(s.get("submitter_id") or "").upper()==sample_id]
    if len(samples)!=1 or samples[0].get("sample_type")!="Primary Tumor":
        raise ValueError("No uniquely matched Primary Tumor source sample for "+pid)
    tissue_day=maybe_float(samples[0].get("days_to_collection"))
    details=[]
    diagnoses=case.get("diagnoses") or []
    for d in diagnoses:
        for t in d.get("treatments") or []:
            answer=str(t.get("treatment_or_therapy") or "").strip().lower()
            if answer not in ("yes","no"):answer="unknown"
            start=maybe_float(t.get("days_to_treatment_start"))
            if answer=="yes":
                if tissue_day is not None and start is not None:
                    relative="YES_ON_OR_BEFORE_TISSUE_DAY" if start<=tissue_day else "YES_AFTER_TISSUE_DAY"
                else:relative="YES_WITHOUT_COMPARABLE_DAY"
            elif answer=="no":
                relative="THERAPY_NOT_ADMINISTERED_IN_THIS_RECORD"
            else:relative="THERAPY_FLAG_UNKNOWN"
            details.append({
                "patient_id":pid,"diagnosis_id":d.get("diagnosis_id") or "",
                "diagnosis_barcode":d.get("submitter_id") or "",
                "prior_treatment":d.get("prior_treatment") or "",
                "diagnosis_day":d.get("days_to_diagnosis") if d.get("days_to_diagnosis") is not None else "",
                "primary_diagnosis":d.get("primary_diagnosis") or "",
                "treatment_id":t.get("treatment_id") or "",
                "treatment_submitter_id":t.get("submitter_id") or "",
                "treatment_or_therapy":answer.upper(),
                "treatment_type":t.get("treatment_type") or "",
                "treatment_intent_type":t.get("treatment_intent_type") or "",
                "treatment_anatomic_sites":"|".join(str(x) for x in
                         (t.get("treatment_anatomic_sites") or [])
                    ) if isinstance(t.get("treatment_anatomic_sites"),list)
                    else str(t.get("treatment_anatomic_sites") or ""),
                "pretreatment_field":t.get("pretreatment") or "",
                "treatment_start_day":start if start is not None else "",
                "treatment_end_day":t.get("days_to_treatment_end") if t.get("days_to_treatment_end") is not None else "",
                "rna_specimen_collection_day":tissue_day if tissue_day is not None else "",
                "relative_treatment_vs_tissue":relative,
                "mri_before_treatment":"NOT_VERIFIED",
                "interpretation":"GDC diagnosis-relative dates are not safely aligned to shifted TCIA MRI dates; treatment might refer to a different episode."
            })
    active=[r for r in details if r["treatment_or_therapy"]=="YES"]
    by_type=Counter(r["relative_treatment_vs_tissue"] for r in active)
    contradictory=sorted({str(d.get("prior_treatment") or "") for d in diagnoses
                         if str(d.get("prior_treatment") or "").strip()})
    if by_type["YES_ON_OR_BEFORE_TISSUE_DAY"]:
        priority="P0_SOURCE_TREATMENT_TIMELINE_REVIEW"
    elif len(contradictory)>1:
        priority="P1_CONFLICTING_DIAGNOSIS_TREATMENT"
    else:
        priority="P2_NO_CONFIRMED_PRETISSUE_YES_BUT_MRI_NOT_DATED"
    summary={
       "patient_id":pid,
       "rna_specimen_collection_day":tissue_day if tissue_day is not None else "",
       "reported_prior_treatment_values":"|".join(contradictory),
       "reported_yes_treatment_records":len(active),
       "yes_treatment_known_day_count":sum(r["treatment_start_day"]!="" for r in active),
       "yes_therapy_start_on_or_before_tissue_count":by_type["YES_ON_OR_BEFORE_TISSUE_DAY"],
       "yes_therapy_start_after_tissue_count":by_type["YES_AFTER_TISSUE_DAY"],
       "yes_therapy_unknown_day_count":by_type["YES_WITHOUT_COMPARABLE_DAY"],
       "diagnoses_with_yes_treatment":len({r["diagnosis_id"] or r["diagnosis_barcode"]
                           for r in active}),
       "absolute_dna_source_sample":"|".join(abs_call["samples"]),
       "absolute_call_status":"|".join(abs_call["call_status"]),
       "absolute_solution":"|".join(abs_call["solution"]),
       "absolute_purity":"|".join(abs_call["purity"]),
       "absolute_ploidy":"|".join(abs_call["ploidy"]),
       "absolute_call_row_count":abs_call["count"],
       "priority":priority,
       "clinical_eligibility":"NOT_ASSESSED",
       "source_limitation":"Original MRI chronology and exact RNA aliquot genomic purity remain NOT_VERIFIED",
    }
    return summary,details


def audit(manifest,cases,abs_calls):
    if len(manifest)!=14 or len(cases)!=14 or len(abs_calls)!=14:
        raise ValueError("Cross-source frozen cohort is incomplete")
    summaries,details=[],[]
    for item in manifest:
        pid=item["patient_id"]
        s,d=flatten(cases[pid],pid,item["aliquot_barcode"],abs_calls[pid])
        summaries.append(s)
        details.extend(d)
    flag={s["patient_id"] for s in summaries
          if s["yes_therapy_start_on_or_before_tissue_count"]>0}
    if flag!=set(P0_IDS):
        # A real source change should trigger manual review and not silently
        # overwrite historical screening or promote/exclude patients.
        raise ValueError("GDC affirmative pre-tissue flagged set drift: "+str(sorted(flag)))
    return summaries,details,{
       "status":"PASS_SOURCE_TREATMENT_AND_PURITY_CALL_METADATA_NOT_ELIGIBILITY",
       "run_utc":datetime.now(timezone.utc).isoformat(),
       "n_frozen_cases":14,"n_detailed_treatments":len(details),
       "reported_yes_therapy_records":sum(s["reported_yes_treatment_records"] for s in summaries),
       "yes_on_or_before_tissue_flag_patients":sorted(flag),
       "yes_after_tissue_only_or_unknown_patient_count":14-len(flag),
       "absolute_call_status_counts":dict(Counter(
           status for s in summaries for status in (s["absolute_call_status"] or "MISSING",).split("|"))),
       "absolute_missing_patients":[s["patient_id"] for s in summaries
                                    if not s["absolute_call_row_count"]],
       "clinical_pretreatment_mri_verified":0,
       "exact_rna_aliquot_genomic_purity_verified":0,
       "final_eligible_patient_count":"NOT_ASSESSED",
       "mri_rna_association_performed":False,
       "claim_ceiling":"S0",
       "note":"Not a clinician adjudication: relative dates may belong to different diagnoses/episodes; impossible to align to TCIA deidentified MRI dates.",
    }


def offline_test():
    aliquot="TCGA-BC-A10Y-01A-11R-A131-07"
    case={"samples":[{"submitter_id":aliquot[:16],"sample_type":"Primary Tumor",
                      "days_to_collection":100}],
          "diagnoses":[
           {"diagnosis_id":"D1","prior_treatment":"No","treatments":[
             {"treatment_id":"T0","treatment_or_therapy":"No","days_to_treatment_start":0},
             {"treatment_id":"T1","treatment_or_therapy":"Yes","days_to_treatment_start":60,
              "treatment_type":"Pharmaceutical Therapy"}]}]}
    abs_call={"count":1,"samples":["TCGA-BC-A10Y-01A"],"call_status":["called"],
              "solution":["1"],"purity":["0.9"],"ploidy":["2.0"]}
    a,detail=flatten(case,"TCGA-BC-A10Y",aliquot,abs_call)
    assert a["yes_therapy_start_on_or_before_tissue_count"]==1
    assert a["reported_yes_treatment_records"]==1
    assert len(detail)==2
    assert detail[0]["relative_treatment_vs_tissue"]=="THERAPY_NOT_ADMINISTERED_IN_THIS_RECORD"
    assert a["clinical_eligibility"]=="NOT_ASSESSED"
    case["diagnoses"][0]["treatments"][1]["days_to_treatment_start"]=200
    b,_=flatten(case,"TCGA-BC-A10Y",aliquot,abs_call)
    assert b["yes_therapy_start_after_tissue_count"]==1
    absrows=load_purity_calls(
      ("array\tsample\tcall status\tpurity\tploidy\tsolution\n"
       "a\tTCGA-BC-A10Y-01A\tcalled\t0.9\t2.0\t1\n").encode(),
      {"TCGA-BC-A10Y":"TCGA-BC-A10Y-01A"})
    assert absrows["TCGA-BC-A10Y"]["status"]=="ONE_SPECIMEN_SOURCE_ROW"
    assert absrows["TCGA-BC-A10Y"]["call_status"]==["called"]
    print("HCC_GDC_TREATMENT_RECORDS_AND_ABSOLUTE_CALL_STATUS_OFFLINE_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--out-dir",default="artifacts/hcc_treatment_detail")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    manifest=inputs()
    patients=[r["patient_id"] for r in manifest]
    cases=get_source_cases(patients)
    raw=fetch_absolute()
    abs_calls=load_purity_calls(raw,{r["patient_id"]:r["aliquot_barcode"][:16]
                                    for r in manifest})
    summaries,details,report=audit(manifest,cases,abs_calls)
    path=Path(args.out_dir);path.mkdir(parents=True,exist_ok=True)
    with (path/"hcc_14_treatment_and_absolute_call_detail.csv").open(
        "w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=RECORD_FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(details)
    with (path/"hcc_14_treatment_absolute_summary.csv").open(
        "w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=SUMMARY_FIELDS,extrasaction="ignore")
        w.writeheader();w.writerows(summaries)
    (path/"hcc_14_source_adjudication_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":
    main()
