#!/usr/bin/env python3
"""HCC Stage45: inspect official GDC public case/files biospecimen lineage for
14 original MRI-identified TCGA-LIHC cases; source-only availability audit.

Technical provenance from Stage44 is frozen, 14 patients; official TCIA
confirms pre-surgical collection (NOT necessarily all HCC treatment-naive) and
privacy-shifted image dates. LiverHccSeg original radiologist readings are
published dataset-level evidence, not a new independent selected ROI approval.
A matching GDC sample→portion→analyte→aliquot is a molecular specimen lineage
proof, NEVER original MRI lesion→sequenced RNA tumor source proof. No biological
association, no eligible N, no clinical GO.

The source API may be temporarily unreachable. Missing/failed requests are
recorded as UNKNOWN or UNAVAILABLE, not as negative biological evidence.
"""
import argparse,csv,hashlib,json,os,time,urllib.parse,urllib.request,urllib.error
from collections import Counter
from pathlib import Path

API="https://api.gdc.cancer.gov"
CASE_FIELDS=(
 "submitter_id","case_id","project.project_id",
 "samples.submitter_id","samples.sample_type","samples.tissue_type",
 "samples.days_to_collection","samples.biospecimen_anatomic_site",
 "samples.tumor_descriptor","samples.portions.submitter_id",
 "samples.portions.analytes.submitter_id",
 "samples.portions.analytes.aliquots.submitter_id",
 "diagnoses.submitter_id","diagnoses.prior_treatment",
 "diagnoses.treatments.treatment_id",
 "diagnoses.treatments.treatment_type",
 "diagnoses.treatments.days_to_treatment_start",
 "diagnoses.treatments.treatment_anatomic_sites"
)
FILE_FIELDS=("file_id","file_name","md5sum","data_type","access",
             "associated_entities.entity_submitter_id",
             "associated_entities.entity_type",
             "cases.submitter_id","cases.case_id")
SOURCE_TCIA="https://www.cancerimagingarchive.net/collection/tcga-lihc/"
SOURCE_ZENODO="https://zenodo.org/records/8179129"
SOURCE_PAPER="https://pmc.ncbi.nlm.nih.gov/articles/PMC10587725/"
GDC_DOC="https://docs.gdc.cancer.gov/API/Users_Guide/Appendix_A_Available_Fields/"

def guard(ok,msg):
    if not ok:raise ValueError(msg)

def readcsv(path):
    with Path(path).open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def get_json(url,tries=3):
    outcome={"status":"NOT_REQUESTED","http_status":None,"bytes":0,"sha256":"",
             "error":"","url":url}
    for attempt in range(tries):
        try:
            req=urllib.request.Request(
                url,headers={"User-Agent":"HCC-Stage45-public-biospecimen-lineage-audit/1.0",
                             "Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=35) as rsp:
                raw=rsp.read(6*1024*1024+1)
                guard(len(raw)<=6*1024*1024,"GDC_PUBLIC_API_RESPONSE_TOO_LARGE")
                outcome.update(status="HTTP_OK",http_status=rsp.status,
                               bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            js=json.loads(raw)
            guard(isinstance(js,dict) and isinstance(js.get("data"),dict),
                  "GDC_API_INVALID_JSON_STRUCTURE")
            return js,outcome
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError,
                ValueError,json.JSONDecodeError) as e:
            outcome["error"]=(type(e).__name__+":"+str(e))[:250]
            outcome["status"]="SOURCE_API_UNAVAILABLE_OR_INVALID"
            if isinstance(e,urllib.error.HTTPError):outcome["http_status"]=e.code
            if attempt+1<tries:time.sleep(min(6,1+2*attempt))
    return None,outcome

def query(endpoint,field,values,fields):
    filters={"op":"in","content":{"field":field,"value":sorted(values)}}
    params={"filters":json.dumps(filters,separators=(",",":")),
            "fields":",".join(fields),"size":"30"}
    url=API+"/"+endpoint+"?"+urllib.parse.urlencode(params)
    doc,result=get_json(url)
    if doc is None:
        minimal=(("submitter_id","case_id","project.project_id",
                  "samples.submitter_id","samples.portions.analytes.aliquots.submitter_id")
                 if endpoint=="cases" else
                 ("file_id","md5sum","associated_entities.entity_submitter_id"))
        fallback_params={"filters":json.dumps(filters,separators=(",",":")),
                         "fields":",".join(minimal),"size":"30"}
        fallback_url=API+"/"+endpoint+"?"+urllib.parse.urlencode(fallback_params)
        retry,rest=get_json(fallback_url,tries=2)
        if retry is not None:
            result=rest
            result["status"]="HTTP_OK_MINIMAL_FIELDS_FALLBACK"
        else:
            result["fallback_error"]=rest["error"]
        doc=retry
    return doc,result

def hits(doc):
    if not doc:return []
    data=doc.get("data",{})
    h=data.get("hits")
    guard(isinstance(h,list),"GDC_QUERY_RETURNED_NO_HITS_ARRAY")
    return h

def flatten_aliquots(case):
    result=[]
    for sample in case.get("samples",[]) or []:
        for portion in sample.get("portions",[]) or []:
            for analyte in portion.get("analytes",[]) or []:
                for aliquot in analyte.get("aliquots",[]) or []:
                    result.append({
                      "sample":str(sample.get("submitter_id","")),
                      "sample_type":str(sample.get("sample_type","")),
                      "site":str(sample.get("biospecimen_anatomic_site","")),
                      "tissue_type":str(sample.get("tissue_type","")),
                      "sample_collection_day":sample.get("days_to_collection"),
                      "portion":str(portion.get("submitter_id","")),
                      "analyte":str(analyte.get("submitter_id","")),
                      "aliquot":str(aliquot.get("submitter_id",""))})
    return result

def case_index(doc,ids):
    found={}
    for obj in hits(doc):
        name=obj.get("submitter_id","")
        guard(name in ids,"GDC_PUBLIC_CASE_RESPONSE_OUTSIDE_FROZEN_COHORT")
        guard(name not in found,"GDC_PUBLIC_CASE_DUPLICATE_HIT")
        found[name]=obj
    return found

def file_index(doc,uuids):
    found={}
    for obj in hits(doc):
        uid=obj.get("file_id","")
        guard(uid in uuids,"GDC_PUBLIC_RNA_FILE_OUTSIDE_FROZEN_COHORT")
        guard(uid not in found,"GDC_PUBLIC_RNA_FILE_DUPLICATE")
        found[uid]=obj
    return found

OUT_FIELDS=(
    "patient_id","priority","MRI_StudyInstanceUID","MRI_SeriesInstanceUID",
    "MRI_index_tumor","RNA_GDC_file_uuid","RNA_GDC_MD5","RNA_aliquot_barcode",
    "public_GDC_case_found","public_GDC_case_id","public_GDC_project_id",
    "public_GDC_nested_biospecimen_aliquot_match",
    "public_GDC_matched_sample","public_GDC_matched_portion",
    "public_GDC_matched_analyte","public_GDC_matched_sample_tissue_type",
    "public_GDC_matched_sample_site","public_GDC_matched_collection_day",
    "public_GDC_file_found","public_GDC_file_md5_consistent",
    "public_GDC_file_associated_aliquot_match",
    "source_link_status","published_radiologist_dataset_reading_exists",
    "new_independent_index_roi_radiologist_review",
    "TCIA_original_scan_collection_statement",
    "specific_MRI_before_any_HCC_treatment",
    "actual_MRI_index_lesion_to_GDC_RNA_tissue_proven",
    "clinical_eligible_n","MRI_RNA_biological_tests","claim_ceiling"
)
def combine(original,cd,fd,cstat,fstat):
    ids={x["patient_id"] for x in original}
    cases=case_index(cd,ids) if cd else {}
    uuids={x["GDC_STAR_RNA_file_UUID"] for x in original}
    files=file_index(fd,uuids) if fd else {}
    out=[]
    for row in original:
        pid=row["patient_id"]
        guard(row["source_PV_image_technical_3d_proven"].startswith("PASS_") and
              row["verified_same_index_MRI_tumor_as_GDC_RNA_aliquot"]=="NOT_ASSESSED" and
              row["verified_original_MRI_before_ALL_relevant_HCC_treatments"]=="NOT_ASSESSED" and
              row["clinical_eligible_n_status"]=="NOT_ASSESSED" and
              row["claim_ceiling"]=="S0","STAGE44_FROZEN_CLINICAL_SOURCE_STATUS_CHANGED")
        uid=row["GDC_STAR_RNA_file_UUID"];aliquot=row["GDC_primary_tumor_RNA_aliquot_barcode"]
        c=cases.get(pid);f=files.get(uid)
        lineages=flatten_aliquots(c) if c else []
        matched=[l for l in lineages if l["aliquot"]==aliquot]
        guard(len(matched)<=1,"GDC_ONE_ALIQUOT_MULTIPLE_TISSUE_SAMPLE_LINEAGES:"+pid)
        matched=matched[0] if matched else None
        associations=f.get("associated_entities",[]) if f else []
        match_f=any(a.get("entity_submitter_id","")==aliquot for a in (associations or []))
        md5=(str(f.get("md5sum","")).lower()==row["GDC_STAR_RNA_md5"].lower()) if f else False
        if f and not md5:
            # The pinned GDC file manifest is an identity source. Reject a
            # public live file with different MD5, not quietly merge it.
            raise ValueError("LIVE_GDC_RNA_FILE_UUID_MD5_MISMATCH:"+pid)
        line_status=("PUBLIC_GDC_CASE_BIOSPECIMEN_ALIQUOT_CHAIN_PRESENT" if matched else
                     "GDC_CASE_AVAILABLE_NESTED_ALIQUOT_NOT_RETURNED" if c else
                     "PUBLIC_GDC_CASE_NOT_RETURNED_OR_UNAVAILABLE")
        result=dict(
          patient_id=pid,priority=row["clinical_evidence_priority"],
          MRI_StudyInstanceUID=row["source_DICOM_StudyInstanceUID"],
          MRI_SeriesInstanceUID=row["source_DICOM_SeriesInstanceUID"],
          MRI_index_tumor=row["frozen_MRI_index_tumor"],
          RNA_GDC_file_uuid=uid,RNA_GDC_MD5=row["GDC_STAR_RNA_md5"],
          RNA_aliquot_barcode=aliquot,
          public_GDC_case_found="YES" if c else "UNKNOWN_NOT_RETURNED",
          public_GDC_case_id=(c or {}).get("case_id",""),
          public_GDC_project_id=(c or {}).get("project",{}).get("project_id",""),
          public_GDC_nested_biospecimen_aliquot_match="YES" if matched else "NOT_RETURNED",
          public_GDC_matched_sample=(matched or {}).get("sample",""),
          public_GDC_matched_portion=(matched or {}).get("portion",""),
          public_GDC_matched_analyte=(matched or {}).get("analyte",""),
          public_GDC_matched_sample_tissue_type=(matched or {}).get("tissue_type",""),
          public_GDC_matched_sample_site=(matched or {}).get("site",""),
          public_GDC_matched_collection_day=(matched or {}).get("sample_collection_day",""),
          public_GDC_file_found="YES" if f else "UNKNOWN_NOT_RETURNED",
          public_GDC_file_md5_consistent="YES" if f and md5 else "NOT_RETURNED",
          public_GDC_file_associated_aliquot_match="YES" if match_f else
             "NOT_RETURNED",
          source_link_status=line_status,
          published_radiologist_dataset_reading_exists="YES_DATASET_LEVEL_ONLY",
          new_independent_index_roi_radiologist_review="NOT_ASSESSED",
          TCIA_original_scan_collection_statement="PRESURGICAL_COLLECTION_LEVEL_NOT_ALL_HCC_TREATMENT_NAIVE",
          specific_MRI_before_any_HCC_treatment="NOT_ASSESSED",
          actual_MRI_index_lesion_to_GDC_RNA_tissue_proven="NOT_ASSESSED",
          clinical_eligible_n="NOT_ASSESSED",
          MRI_RNA_biological_tests=0,claim_ceiling="S0")
        guard(set(result)==set(OUT_FIELDS),"STAGE45_RESULT_FIELD_DRIFT")
        out.append(result)
    summary=dict(stage="HCC_STAGE45_PUBLIC_GDC_BIOSPECIMEN_LINEAGE_AND_SOURCE_FEASIBILITY",
       pinned_original_MRI_UID_GDC_case_count=len(out),
       original_DICOM_PV_NIfTI_technical_source_verified_n=14,
       published_LiverHccSeg_dataset_board_certified_readers=2,
       independent_current_index_roi_radiologist_approved_n=0,
       GDC_public_cases_query_status=cstat["status"],
       GDC_public_files_query_status=fstat["status"],
       GDC_public_cases_returned=len(cases),
       GDC_public_RNA_files_returned=len(files),
       case_level_public_biospecimen_aliquot_chains_returned=sum(
            r["public_GDC_nested_biospecimen_aliquot_match"]=="YES" for r in out),
       public_RNA_file_UUID_MD5_matches=sum(
            r["public_GDC_file_md5_consistent"]=="YES" for r in out),
       public_RNA_file_associated_aliquot_matches=sum(
            r["public_GDC_file_associated_aliquot_match"]=="YES" for r in out),
       source_TCIA_collection_level_presurgical_statement=True,
       pretreatment_HCC_specific_authoritative_episode_verified_n=0,
       MRI_selected_index_lesion_to_RNA_aliquot_physical_bridge_verified_n=0,
       TCIADICOM_shifted_dates_subtract_GDC_relative_days_allowed=False,
       clinical_eligible_n="NOT_ASSESSED",MRI_RNA_biological_tests=0,claim_ceiling="S0",
       source_paper=SOURCE_PAPER,source_tcia=SOURCE_TCIA,source_zenodo=SOURCE_ZENODO,
       source_gdc_public_api=GDC_DOC,
       decision="GDC_BIOSPECIMEN_METADATA_AVAILABILITY_REVIEW_NO_CLINICAL_GO")
    guard(len(out)==14 and len(set(r["patient_id"] for r in out))==14,
          "STAGE45_FROZEN_COHORT_NOT_COMPLETE")
    return out,summary

def write(out,rows,summary,checks):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stage45_public_GDC_molecular_biospecimen_source_14case.csv").open(
        "w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=OUT_FIELDS)
        w.writeheader();w.writerows(rows)
    (out/"stage45_gdc_public_api_source_requests.json").write_text(
        json.dumps(checks,indent=2)+"\n")
    (out/"stage45_public_source_biospecimen_feasibility_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    lines=[
      "# HCC Stage45 public molecular sample lineage and MRI clinical pairing source feasibility",
      "", "**Frozen original MRI DICOM ↔ native PV NIfTI 14/14 source-image GO.**",
      "The original LiverHccSeg dataset had two board-certified radiologists perform scientific image readings;",
      "a new blinded independent review of each currently selected index lesion is NOT_ASSESSED.",
      "TCIA says its TCGA-LIHC baseline images are pre-surgical; this is not an all-HCC-therapy-before-scan assurance.",
      "TCIA DICOM shifted dates cannot be directly subtracted from GDC diagnosis-relative treatment/sample days.",
      "", "Live public GDC cases: "+summary["GDC_public_cases_query_status"]+
          "; public RNA files: "+summary["GDC_public_files_query_status"]+".",
      "Patients with explicitly returned sample→portion→analyte→aliquot lineage: "+
          str(summary["case_level_public_biospecimen_aliquot_chains_returned"])+"/14.",
      "Verified GDC RNA file UUID/MD5 from live file metadata: "+
          str(summary["public_RNA_file_UUID_MD5_matches"])+"/14.",
      "Neither one is proof the RNA sample came from the MRI-selected index lesion.",
      "HCC treatment episode timing confirmed 0/14; MRI index-lesion-to-aliquot bridge 0/14;",
      "eligible N NOT_ASSESSED, frozen MRI–RNA tests 0/12, claim ceiling S0.",
      "","| Patient | GDC case | Public exact molecular aliquot chain | RNA file MD5 | Clinical MRI-RNA |",
      "|---|---|---|---|---|"]
    for r in rows:
        lines.append("| "+r["patient_id"]+" | "+r["public_GDC_case_found"]+" | "+
          r["public_GDC_nested_biospecimen_aliquot_match"]+" | "+
          r["public_GDC_file_md5_consistent"]+" | HOLD |")
    report="\n".join(lines)+"\n"
    (out/"stage45_public_GDC_original_case_biospecimen_source_report.md").write_text(report)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE45_PUBLIC_GDC_SOURCE_FEASIBILITY",
          json.dumps(summary,sort_keys=True),flush=True)

def offline():
    assert len(CASE_FIELDS)>=10 and len(FILE_FIELDS)>=6
    assert "samples.portions.analytes.aliquots.submitter_id" in CASE_FIELDS
    assert "associated_entities.entity_submitter_id" in FILE_FIELDS
    assert "actual_MRI_index_lesion_to_GDC_RNA_tissue_proven" in OUT_FIELDS
    guard(not bool([x for x in OUT_FIELDS if "days_shift_subtraction" in x]),
          "UNAUTHORIZED_SOURCE_DATE_SUBTRACTION")
    print("HCC_STAGE45_CASE_ALIQUOT_SOURCE_CHAIN_NEGATIVE_CLINICAL_GO_TEST_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage44-csv",type=Path)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage45_public_gdc"))
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    offline()
    if args.offline_test:return
    guard(args.stage44_csv and args.stage44_csv.is_file(),
          "STAGE44_FROZEN_UID_RNA_EVIDENCE_CSV_REQUIRED")
    original=readcsv(args.stage44_csv)
    guard(len(original)==14 and len({x["patient_id"] for x in original})==14,
          "STAGE44_CLINICAL_14_ROW_SOURCE_MISMATCH")
    cases,cs=query("cases","submitter_id",{x["patient_id"] for x in original},CASE_FIELDS)
    files,fs=query("files","file_id",{x["GDC_STAR_RNA_file_UUID"] for x in original},FILE_FIELDS)
    rows,summary=combine(original,cases,files,cs,fs)
    write(args.out_dir,rows,summary,{"cases":cs,"files":fs})
if __name__=="__main__":main()
