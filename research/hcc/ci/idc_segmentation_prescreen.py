#!/usr/bin/env python3
"""IDC TCGA-LIHC DICOM SEG label/source-CT metadata prescreen.

Uses public IDC v3 SQL API. Never downloads images or masks.
Segmentation labels must not be considered tumor ROI proof before image review.
API failure is reported as NOT_VERIFIED (no invented zero counts).
"""
import argparse
import csv
import json
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

API="https://api.imaging.datacommons.cancer.gov/v3/sql"
TUMOR=re.compile(r"tumou?r|neoplasm|malignan|lesion|hepatocellular|carcinoma",re.I)
LIVER=re.compile(r"\bliver\b|hepatic",re.I)
VALID_ID=re.compile(r"^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$")
QUERY = """
SELECT i.PatientID AS patient_id,
       i.SeriesInstanceUID AS seg_series_uid,
       i.SeriesDescription AS segmentation_series_description,
       i.analysis_result_id AS analysis_result_id,
       s.SegmentedPropertyType_CodeMeanings AS segmentation_labels,
       s.segmented_SeriesInstanceUID AS referenced_ct_series
FROM index i
JOIN seg_index s ON s.SeriesInstanceUID = i.SeriesInstanceUID
WHERE i.collection_id = 'tcga_lihc'
  AND i.Modality = 'SEG'
LIMIT 3000
"""


def post_sql(query):
    body=json.dumps({"sql":query,"max_rows":3000}).encode("utf-8")
    req=urllib.request.Request(API,data=body,headers={
        "Accept":"application/json","Content-Type":"application/json",
        "User-Agent":"HCC-CT-RNA-metadata-audit/1.0"},method="POST")
    with urllib.request.urlopen(req,timeout=90) as response:
        payload=json.load(response)
    if not isinstance(payload,dict):
        raise ValueError("Unexpected IDC SQL API response root")
    if payload.get("truncated") is True:
        raise RuntimeError("IDC SQL returned truncated data; cannot assume complete cohort")
    rows=payload.get("rows")
    if rows is None:
        rows=payload.get("results")
    if rows is None and isinstance(payload.get("data"),dict):
        rows=payload["data"].get("rows")
    if rows is None and isinstance(payload.get("data"),list):
        rows=payload["data"]
    if not isinstance(rows,list):
        raise ValueError("Unknown IDC response schema; keys="+",".join(payload))
    if rows and not isinstance(rows[0],dict):
        raise ValueError("IDC returned non-object SQL rows; inspect schema")
    return rows


def strings(obj):
    if obj is None:
        return []
    if isinstance(obj,(list,tuple)):
        return [s for i in obj for s in strings(i)]
    if isinstance(obj,dict):
        return [s for k,v in obj.items() for s in strings(v)]
    return [str(obj)]


def label_class(value):
    text=" ".join(strings(value))
    if "tumor infiltration by lymphocytes" in text.lower() or "tumor-infiltrating lymphocytes" in text.lower():
        return "HISTOPATHOLOGY_TIL_ANNOTATION_NOT_TUMOR_MASK"
    if TUMOR.search(text):
        return "POSSIBLE_TUMOR_SEG_LABEL_REVIEW"
    if LIVER.search(text):
        return "LIVER_ORGAN_SEG_ONLY"
    return "UNSPECIFIED_SEG_LABEL_REVIEW"


def audit(rows, ct_rows, matched_ids):
    ct_lookup={(r["PatientID"],r["SeriesInstanceUID"])
               for r in ct_rows if r["PatientID"] in matched_ids}
    patient_rows, matching_rows=[],[]
    by_patient={pid:[] for pid in matched_ids}
    for row in rows:
        pid=str(row.get("patient_id") or "").upper()
        if pid not in by_patient:
            continue
        src_ids=set(strings(row.get("referenced_ct_series")))
        if not src_ids:
            src_ids=set()
        ct_overlap=sorted(uid for uid in src_ids if (pid,uid) in ct_lookup)
        item={
            "patient_id":pid,
            "seg_series_uid":str(row.get("seg_series_uid") or ""),
            "segmentation_labels":"|".join(strings(row.get("segmentation_labels"))),
            "segmentation_label_class":label_class(row.get("segmentation_labels")),
            "referenced_ct_series":"|".join(sorted(src_ids)),
            "references_tcia_ct_series":"YES" if ct_overlap else "NO_OR_NOT_REPORTED",
            "referenced_tcia_ct_series":"|".join(ct_overlap),
            "actual_tumor_mask_verified":"NO",
        }
        matching_rows.append(item)
        by_patient[pid].append(item)
    for pid in sorted(matched_ids):
        p=by_patient[pid]
        c=Counter(x["segmentation_label_class"] for x in p)
        suspected=[x for x in p if x["segmentation_label_class"]=="POSSIBLE_TUMOR_SEG_LABEL_REVIEW"
                   and x["references_tcia_ct_series"]=="YES"]
        referenced_liver=[x for x in p if x["segmentation_label_class"]=="LIVER_ORGAN_SEG_ONLY"
                          and x["references_tcia_ct_series"]=="YES"]
        patient_rows.append({
            "patient_id":pid,
            "idc_seg_series":len(p),
            "possible_tumor_label_series":c["POSSIBLE_TUMOR_SEG_LABEL_REVIEW"],
            "liver_only_label_series":c["LIVER_ORGAN_SEG_ONLY"],
            "liver_seg_references_tcia_ct":len(referenced_liver),
            "histopathology_til_annotations":c["HISTOPATHOLOGY_TIL_ANNOTATION_NOT_TUMOR_MASK"],
            "other_label_series":c["UNSPECIFIED_SEG_LABEL_REVIEW"],
            "possible_tumor_seg_references_tcia_ct":"YES" if suspected else "NO",
            "actual_tumor_mask_verified":"NO",
            "ct_rna_radiogenomics_eligible":"NOT_ASSESSED",
        })
    summary={
        "status":"PASS_IDC_SEG_METADATA_ONLY",
        "matched_ct_rna_patients":len(matched_ids),
        "matched_patient_seg_series":len(matching_rows),
        "patients_with_any_seg":sum(p["idc_seg_series"]>0 for p in patient_rows),
        "patients_with_possible_tumor_seg_labels":sum(p["possible_tumor_label_series"]>0 for p in patient_rows),
        "patients_with_tcia_ct_referenced_liver_seg":sum(
            p["liver_seg_references_tcia_ct"]>0 for p in patient_rows),
        "tcia_ct_referenced_liver_seg_series":sum(
            p["liver_seg_references_tcia_ct"] for p in patient_rows),
        "histopathology_til_annotation_series":sum(
            p["histopathology_til_annotations"] for p in patient_rows),
        "patients_with_possible_tumor_seg_referenced_to_tcia_ct":sum(
            p["possible_tumor_seg_references_tcia_ct"]=="YES" for p in patient_rows),
        "qualified_ct_roi_rna_pairs":"NOT_ASSESSED",
        "warning":"Segment labels and referenced UIDs are only metadata; tumor ROI and anatomy require image review."
    }
    return matching_rows,patient_rows,summary


def input_rows(path, cols):
    with open(path,encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        if not reader.fieldnames or not set(cols).issubset(reader.fieldnames):
            raise ValueError("Missing "+str(cols)+" in "+path)
        return list(reader)


def offline_test():
    assert label_class(["Liver"])=="LIVER_ORGAN_SEG_ONLY"
    assert label_class(["Hepatic Tumor"])=="POSSIBLE_TUMOR_SEG_LABEL_REVIEW"
    assert label_class(["Tumor infiltration by lymphocytes present"])=="HISTOPATHOLOGY_TIL_ANNOTATION_NOT_TUMOR_MASK"
    assert label_class(None)=="UNSPECIFIED_SEG_LABEL_REVIEW"
    ct=[{"PatientID":"TCGA-AA-0001","SeriesInstanceUID":"CT-ONE"}]
    segments=[
        {"patient_id":"TCGA-AA-0001","seg_series_uid":"SEG1",
         "segmentation_labels":["Liver"],"referenced_ct_series":"CT-ONE"},
        {"patient_id":"TCGA-AA-0001","seg_series_uid":"SEG2",
         "segmentation_labels":["Liver tumor"],"referenced_ct_series":"CT-ONE"}]
    _, patients, summary=audit(segments,ct,{"TCGA-AA-0001"})
    assert summary["patients_with_possible_tumor_seg_referenced_to_tcia_ct"]==1
    assert patients[0]["actual_tumor_mask_verified"]=="NO"
    print("HCC_IDC_TUMOR_SEGMENTATION_PRESCREEN_OFFLINE_TEST_PASS")


def write_csv(path,rows,fields):
    with open(path,"w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ct-csv",default="artifacts/hcc_tcia/TCGA-LIHC_ct_series.csv")
    parser.add_argument("--matches-csv",default="artifacts/hcc_tcia/tcga_rna_overlap_candidates.csv")
    parser.add_argument("--output",default="artifacts/hcc_tcia")
    parser.add_argument("--offline-test",action="store_true")
    args=parser.parse_args()
    if args.offline_test:
        offline_test()
        return
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    cts=input_rows(args.ct_csv,{"PatientID","SeriesInstanceUID"})
    ids={r["patient_id"] for r in input_rows(args.matches_csv,{"patient_id"})}
    if not ids or any(not VALID_ID.fullmatch(pid) for pid in ids):
        raise ValueError("No/invalid TCGA matched patient barcodes")
    try:
        rows=post_sql(QUERY)
        seg,patients,summary=audit(rows,cts,ids)
        write_csv(out/"tcga_idc_segmentation_metadata.csv",seg,
                  ["patient_id","seg_series_uid","segmentation_labels","segmentation_label_class",
                   "referenced_ct_series","references_tcia_ct_series",
                   "referenced_tcia_ct_series","actual_tumor_mask_verified"])
        write_csv(out/"tcga_idc_roi_patient_screen.csv",patients,list(patients[0]))
    except Exception as exc:
        summary={"status":"IDC_SEGMENTATION_METADATA_NOT_VERIFIED",
                 "error_class":type(exc).__name__,
                 "error":str(exc)[:500],
                 "matched_ct_rna_patients":len(ids),
                 "qualified_ct_roi_rna_pairs":"NOT_ASSESSED",
                 "warning":"Failed external IDC metadata query; no zero count implied."}
    (out/"tcga_idc_segmentation_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
