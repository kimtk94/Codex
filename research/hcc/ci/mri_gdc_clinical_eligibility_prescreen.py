#!/usr/bin/env python3
"""TCGA-LIHC 14-patient GDC clinical/treatment/sample annotation prescreen.

Read-only public GDC cases API; no DICOM-date comparisons, no assumptions that
prior_treatment='No' proves the archived MRI pre-treatment or same-lesion.
Fail closed for missing cases, mismatch, invalid sample lineage and time.
No clinical fields automatically promote MRI-RNA paired-cohort eligibility.
"""
import argparse
import csv
import json
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

GDC="https://api.gdc.cancer.gov/cases"
SOURCE="research/hcc/HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv"
FIELDS=(
 "submitter_id","case_id","project.project_id","tissue_source_site.tissue_source_site_id",
 "diagnoses.primary_diagnosis","diagnoses.tumor_grade","diagnoses.ajcc_pathologic_stage",
 "diagnoses.prior_treatment","diagnoses.days_to_diagnosis",
 "diagnoses.treatments.treatment_or_therapy","diagnoses.treatments.treatment_type",
 "diagnoses.treatments.days_to_treatment_start",
 "diagnoses.treatments.pretreatment",
 "samples.submitter_id","samples.sample_type","samples.tissue_type",
 "samples.tumor_descriptor","samples.days_to_collection",
 "samples.portions.slides.percent_tumor_cells",
 "samples.portions.slides.percent_tumor_nuclei"
)
OUTPUT=(
 "patient_id","case_found","rna_aliquot_barcode","gdc_primary_tumor_sample_matched",
 "gdc_sample_type","gdc_sample_tissue_type","gdc_sample_tumor_descriptor",
 "sample_days_to_collection","tss_code","gdc_primary_diagnosis",
 "gdc_pathologic_stage","gdc_tumor_grade",
 "prior_treatment_values","prior_treatment_screen",
 "n_reported_treatment_records","reported_treatment_types",
 "earliest_recorded_treatment_day","treatment_timing_screen",
 "linked_slide_purity_n","linked_slide_tumor_cells_min",
 "linked_slide_tumor_nuclei_min","rna_tumor_purity_screen",
 "mri_source_baseline_presurgical_policy",
 "mri_to_tissue_pretherapy_temporal_confirmation",
 "mri_roi_expert_review","final_radiogenomics_eligibility",
 "exclusion_or_review_reason"
)

def inputs(path=SOURCE):
    with open(path,encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    ids=[r["patient_id"] for r in rows]
    if len(rows)!=14 or len(set(ids))!=14:
        raise ValueError("Require 14 unique source-verified patients")
    for r in rows:
        if not r["aliquot_barcode"].startswith(r["patient_id"]+"-01"):
            raise ValueError("Aliquot is not matched TCGA primary tumor")
    return sorted(rows,key=lambda r:r["patient_id"])

def get_cases(patients):
    f={"op":"and","content":[
       {"op":"in","content":{"field":"submitter_id","value":patients}},
       {"op":"in","content":{"field":"project.project_id","value":["TCGA-LIHC"]}}
    ]}
    params=urllib.parse.urlencode({
       "filters":json.dumps(f,separators=(",",":")),
       "fields":",".join(FIELDS),"format":"JSON","size":100
    })
    req=urllib.request.Request(GDC+"?"+params,
       headers={"Accept-Encoding":"identity","User-Agent":"HCC-Clinical-Frozen-14-Audit/1.0"})
    with urllib.request.urlopen(req,timeout=70) as response:
        body=response.read(5*1024*1024+1)
    if len(body)>5*1024*1024:raise ValueError("GDC cases response too large")
    result=json.loads(body)
    data=result.get("data") or {}
    hits=data.get("hits")
    if not isinstance(hits,list):raise ValueError("GDC cases JSON schema invalid")
    if (data.get("pagination") or {}).get("total")!=len(patients):
        raise ValueError("GDC returned incomplete or unexpectedly many cases")
    return hits

def is_empty(v):
    return v is None or str(v).strip().lower() in (
        "","not reported","not available","unknown","--","null")

def norm_value(v):
    return "" if is_empty(v) else str(v).strip()

def maybe_float(v):
    try:
        if is_empty(v):return None
        return float(v)
    except (ValueError,TypeError):return None

def retrieve_case(row,hit):
    pid=row["patient_id"]
    out={key:"" for key in OUTPUT}
    out.update(
        patient_id=pid,
        rna_aliquot_barcode=row["aliquot_barcode"],
        final_radiogenomics_eligibility="NOT_ASSESSED",
        mri_to_tissue_pretherapy_temporal_confirmation="NOT_VERIFIED",
        mri_roi_expert_review="NOT_VERIFIED",
        mri_source_baseline_presurgical_policy="TCIA_BASELINE_COLLECTION_LEVEL_ONLY",
        rna_tumor_purity_screen="UNKNOWN_NOT_INDICATIVE_OF_ABSOLUTE_PURITY",
        treatment_timing_screen="MRI_TO_GDC_RELATIVE_OFFSET_NOT_AVAILABLE",
    )
    if hit is None:
        out.update(case_found="NO",gdc_primary_tumor_sample_matched="NO",
                   exclusion_or_review_reason="MISSING_GDC_CASE")
        return out
    if hit.get("submitter_id")!=pid or (hit.get("project") or {}).get("project_id")!="TCGA-LIHC":
        raise ValueError("GDC patient/project mismatch")
    out["case_found"]="YES"
    # TSS from frozen barcode, not a claim of imaging scanner identity.
    out["tss_code"]=pid.split("-")[1]
    ds=hit.get("diagnoses") or []
    prior=sorted({norm_value(d.get("prior_treatment")) for d in ds
                  if not is_empty(d.get("prior_treatment"))})
    out["prior_treatment_values"]="|".join(prior)
    low={p.lower() for p in prior}
    if not prior:
        out["prior_treatment_screen"]="UNKNOWN_NO_DIAGNOSIS_STATUS"
    elif low=={"no"}:
        out["prior_treatment_screen"]="REPORTED_NO_PRIOR_TREATMENT_AT_DIAGNOSIS"
    else:
        out["prior_treatment_screen"]="POSSIBLE_PRIOR_TREATMENT_OR_AMBIGUOUS"
    primary=next((d for d in ds if d.get("primary_diagnosis")),ds[0] if ds else {})
    out["gdc_primary_diagnosis"]=norm_value(primary.get("primary_diagnosis"))
    out["gdc_pathologic_stage"]=norm_value(primary.get("ajcc_pathologic_stage"))
    out["gdc_tumor_grade"]=norm_value(primary.get("tumor_grade"))
    treatments=[t for d in ds for t in (d.get("treatments") or [])
                if isinstance(t,dict)]
    out["n_reported_treatment_records"]=len(treatments)
    out["reported_treatment_types"]="|".join(sorted({
         norm_value(t.get("treatment_type")) for t in treatments
         if not is_empty(t.get("treatment_type"))}))
    days=[maybe_float(t.get("days_to_treatment_start")) for t in treatments]
    dates=[d for d in days if d is not None]
    if dates:out["earliest_recorded_treatment_day"]=min(dates)
    # No TCIA MRI day on GDC's pathological-diagnosis-relative scale,
    # so a treatment day cannot establish that the MRI preceded therapy.
    code=row["aliquot_barcode"][:16] # TCGA-XX-XXXX-01A prefix
    sample_candidates=[s for s in (hit.get("samples") or [])
              if str(s.get("submitter_id") or "").upper()==code.upper()]
    out["gdc_primary_tumor_sample_matched"]="YES" if len(sample_candidates)==1 else "NO"
    reasons=[]
    if len(sample_candidates)!=1:
        reasons.append("MISSING_OR_DUPLICATE_EXACT_PRIMARY_TUMOR_SAMPLE")
    else:
        s=sample_candidates[0]
        out["gdc_sample_type"]=norm_value(s.get("sample_type"))
        out["gdc_sample_tissue_type"]=norm_value(s.get("tissue_type"))
        out["gdc_sample_tumor_descriptor"]=norm_value(s.get("tumor_descriptor"))
        day=maybe_float(s.get("days_to_collection"))
        if day is not None:out["sample_days_to_collection"]=day
        relevant_slides=[slide for portion in (s.get("portions") or [])
            for slide in (portion.get("slides") or []) if isinstance(slide,dict)]
        cell=[maybe_float(slide.get("percent_tumor_cells")) for slide in relevant_slides]
        nuclei=[maybe_float(slide.get("percent_tumor_nuclei")) for slide in relevant_slides]
        cell=[x for x in cell if x is not None]
        nuclei=[x for x in nuclei if x is not None]
        out["linked_slide_purity_n"]=len(relevant_slides)
        if cell:out["linked_slide_tumor_cells_min"]=min(cell)
        if nuclei:out["linked_slide_tumor_nuclei_min"]=min(nuclei)
        if cell or nuclei:
            out["rna_tumor_purity_screen"]="LINKED_SLIDE_PERCENT_AVAILABLE_NOT_GENOMIC_PURITY"
        if out["gdc_sample_type"]!="Primary Tumor":
            reasons.append("SAMPLE_TYPE_NOT_PRIMARY_TUMOR")
    if out["prior_treatment_screen"]!="REPORTED_NO_PRIOR_TREATMENT_AT_DIAGNOSIS":
        reasons.append("PRIOR_TREATMENT_NEEDS_REVIEW")
    reasons.extend(["MRI_TISSUE_CHRONOLOGY_UNVERIFIED",
                    "ROI_EXPERT_REVIEW_UNVERIFIED"])
    out["exclusion_or_review_reason"]="|".join(reasons)
    return out

def summarize(items,rows):
    cases={x["submitter_id"]:x for x in rows}
    if len(cases)!=len(rows):
        raise ValueError("Duplicate GDC case")
    if set(cases)!={x["patient_id"] for x in items}:
        raise ValueError("GDC patient ids mismatch")
    matched=[retrieve_case(x,cases.get(x["patient_id"])) for x in items]
    status=Counter(x["prior_treatment_screen"] for x in matched)
    return matched,{
        "status":"PASS_GDC_CLINICAL_PRESCREEN_NOT_TEMPORAL_ELIGIBILITY",
        "run_utc":datetime.now(timezone.utc).isoformat(),
        "case_count":len(matched),
        "case_found":sum(x["case_found"]=="YES" for x in matched),
        "exact_primary_tumor_samples":sum(x["gdc_primary_tumor_sample_matched"]=="YES" for x in matched),
        "prior_treatment_disclosure_counts":dict(status),
        "patients_with_linked_slide_purity_percent":sum(
            bool(x["linked_slide_tumor_cells_min"]!="") or
            bool(x["linked_slide_tumor_nuclei_min"]!="") for x in matched),
        "confirmed_mri_before_therapy":0,
        "expert_roi_confirmed":0,
        "fully_qualified_paired_patients":"NOT_ASSESSED",
        "warnings":[
          "TCIA baseline image is pre-surgical at COLLECTION level, not proof of being untreated or pre-tissue for this exact MRI.",
          "GDC treatment day values are relative to diagnosis, TCIA image dates are independently shifted; absolute joins prohibited.",
          "No reporting of treatment is not proof of absence of treatment.",
          "GDC slide percent tumor cells/nuclei is not ABSOLUTE genetic purity and may represent a different portion.",
        ],
    }

def offline_test():
    case={
      "submitter_id":"TCGA-AA-0001","project":{"project_id":"TCGA-LIHC"},
      "diagnoses":[{"prior_treatment":"No","primary_diagnosis":"Hepatocellular carcinoma",
                    "treatments":[{"treatment_type":"Pharmaceutical Therapy",
                     "days_to_treatment_start":30}]}],
      "samples":[{"submitter_id":"TCGA-AA-0001-01A","sample_type":"Primary Tumor",
                  "portions":[{"slides":[{"percent_tumor_cells":75,
                                         "percent_tumor_nuclei":70}]}]}],
    }
    row={"patient_id":"TCGA-AA-0001",
         "aliquot_barcode":"TCGA-AA-0001-01A-11R-XXXX-07"}
    a=retrieve_case(row,case)
    assert a["gdc_primary_tumor_sample_matched"]=="YES"
    assert a["prior_treatment_screen"]=="REPORTED_NO_PRIOR_TREATMENT_AT_DIAGNOSIS"
    assert a["rna_tumor_purity_screen"]=="LINKED_SLIDE_PERCENT_AVAILABLE_NOT_GENOMIC_PURITY"
    assert a["mri_to_tissue_pretherapy_temporal_confirmation"]=="NOT_VERIFIED"
    assert a["final_radiogenomics_eligibility"]=="NOT_ASSESSED"
    b=retrieve_case(row,{"submitter_id":"TCGA-AA-0001",
          "project":{"project_id":"TCGA-LIHC"},"diagnoses":[],"samples":[]})
    assert "MISSING_OR_DUPLICATE" in b["exclusion_or_review_reason"]
    print("HCC_CLINICAL_PRETREATMENT_GDC_FAIL_CLOSED_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--output",default="artifacts/hcc_gdc_clinical")
    p.add_argument("--manifest",default=SOURCE)
    args=p.parse_args()
    if args.offline_test:return offline_test()
    items=inputs(args.manifest)
    data=get_cases([x["patient_id"] for x in items])
    records,info=summarize(items,data)
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    with (root/"hcc_gdc_14_clinical_temporal_prescreen.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=OUTPUT);w.writeheader();w.writerows(records)
    (root/"hcc_gdc_14_clinical_temporal_summary.json").write_text(
        json.dumps(info,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(info,ensure_ascii=False))
    if info["case_found"]!=14:
        raise SystemExit("GDC clinical prescreen incomplete, retain gate HOLD")

if __name__=="__main__":
    main()
