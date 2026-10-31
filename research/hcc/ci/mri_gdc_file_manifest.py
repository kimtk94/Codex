#!/usr/bin/env python3
"""Strict MRI HCC tumor-mask patient -> GDC STAR-Counts RNA file manifest.

No expression data is downloaded. File-specific aliquot/sample barcode code '01'
is required. Conflicts/multiple files are marked review-required, not silently
resolved. md5sum and file_size are GDC metadata and must be verified at download.
"""
import argparse
import csv
import json
import re
import urllib.parse
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

from tcga_rna_overlap_audit import (
    GDC_URL, gdc_filter, fetch_json, normalize_id,
)
from gdc_tumor_lineage_audit import classify_file

FIELDS = (
    "patient_id","gdc_file_id","gdc_file_name","gdc_file_size_bytes",
    "gdc_md5sum","file_associated_aliquot_or_sample_ids",
    "sample_type_code","file_specific_tumor_lineage_status",
    "patient_file_selection_status","counts_downloaded","numeric_rna_qc",
    "tumor_expression_matrix_eligible"
)
EXTENDED_FIELDS=(
    "file_id,file_name,file_size,md5sum,data_type,analysis.workflow_type,"
    "cases.submitter_id,associated_entities.entity_submitter_id,"
    "associated_entities.entity_type"
)


def fetch_files(page_size=500):
    out=[]
    offset=0
    while True:
        params=urllib.parse.urlencode({
            "filters":json.dumps(gdc_filter(),separators=(",",":")),
            "fields":EXTENDED_FIELDS,"format":"JSON",
            "from":offset,"size":page_size,
        })
        data=(fetch_json(GDC_URL+"?"+params).get("data") or {})
        hits=data.get("hits")
        total=(data.get("pagination") or {}).get("total")
        if not isinstance(hits,list) or total is None:
            raise ValueError("GDC file metadata pagination invalid")
        out.extend(hits)
        offset+=len(hits)
        if offset>=int(total):
            return out
        if not hits:
            raise RuntimeError("GDC pagination stalled")


def candidates_from_mask_qc(rows):
    result=set()
    seen=set()
    for row in rows:
        p=row["patient_id"]
        if p in seen:
            raise ValueError("Duplicate MRI patient in mask QC")
        seen.add(p)
        if not re.fullmatch(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}",p):
            raise ValueError("Malformed TCGA patient barcode")
        if row["nifti_mask_voxel_status"]=="PASS_NONEMPTY_NIFTI_MASK":
            result.add(p)
    if not result:
        raise ValueError("No mask-QC-passed patient IDs")
    return result


def build(files, patient_ids):
    matches=defaultdict(list)
    for f in files:
        if f.get("data_type")!="Gene Expression Quantification":
            continue
        if (f.get("analysis") or {}).get("workflow_type")!="STAR - Counts":
            continue
        fid=f.get("file_id") or f.get("id")
        if not fid:
            continue
        seen=set()
        for case in f.get("cases") or []:
            patient=normalize_id(case.get("submitter_id"))
            if patient not in patient_ids or patient in seen:
                continue
            seen.add(patient)
            code,status,_=classify_file(f,patient)
            if status!="PRIMARY_TUMOR_FILE_BARCODE_LINKED":
                continue
            associated=sorted(set(str(ent.get("entity_submitter_id","")).upper()
                                  for ent in f.get("associated_entities") or []
                                  if isinstance(ent,dict) and ent.get("entity_submitter_id")))
            matches[patient].append({
                "patient_id":patient,"gdc_file_id":fid,
                "gdc_file_name":f.get("file_name",""),
                "gdc_file_size_bytes":f.get("file_size") or "",
                "gdc_md5sum":f.get("md5sum") or "",
                "file_associated_aliquot_or_sample_ids":"|".join(associated),
                "sample_type_code":code,
                "file_specific_tumor_lineage_status":status,
                "counts_downloaded":"NO","numeric_rna_qc":"NOT_ASSESSED",
                "tumor_expression_matrix_eligible":"NOT_ASSESSED",
            })
    records=[]
    for pid in sorted(patient_ids):
        files_for_pid=sorted(matches.get(pid,[]),key=lambda r:r["gdc_file_id"])
        if not files_for_pid:
            records.append({
                "patient_id":pid,"gdc_file_id":"","gdc_file_name":"",
                "file_specific_tumor_lineage_status":"NO_FILE_LINK",
                "patient_file_selection_status":"BLOCKED_NO_TUMOR_RNA_FILE",
                "counts_downloaded":"NO","numeric_rna_qc":"NOT_ASSESSED",
                "tumor_expression_matrix_eligible":"NOT_ASSESSED",
            })
        else:
            for r in files_for_pid:
                r["patient_file_selection_status"]=(
                    "ONE_PRIMARY_TUMOR_FILE_METADATA_CANDIDATE"
                    if len(files_for_pid)==1 else "MULTIPLE_PRIMARY_TUMOR_FILES_REVIEW")
                records.append(r)
    patient_status={}
    for pid in patient_ids:
        r=[x for x in records if x["patient_id"]==pid]
        patient_status[pid]=r[0]["patient_file_selection_status"]
    hist=Counter(patient_status.values())
    summary={
        "status":"PASS_STRICT_FILE_MANIFEST_METADATA_ONLY",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "tumor_mask_pixel_qc_patient_candidates":len(patient_ids),
        "patients_with_one_tumor_rna_file":hist["ONE_PRIMARY_TUMOR_FILE_METADATA_CANDIDATE"],
        "patients_with_multiple_tumor_rna_files":hist["MULTIPLE_PRIMARY_TUMOR_FILES_REVIEW"],
        "patients_without_verified_file":hist["BLOCKED_NO_TUMOR_RNA_FILE"],
        "total_file_patient_records":len(records),
        "numeric_counts_verified_patients":0,
        "radiogenomics_eligible_patient_count":"NOT_ASSESSED",
        "warnings":[
            "A single file metadata match is not proof of RNA quality, correct gene identifiers or clinical timing.",
            "md5sum is a download integrity target; no count matrices were fetched.",
            "Never silently choose a file if a case contains multiple Primary Tumor aliquots."
        ],
    }
    return records,summary


def offline_test():
    a={"file_id":"fileA","file_name":"counts.tsv","file_size":1100,"md5sum":"0"*32,
       "data_type":"Gene Expression Quantification",
       "analysis":{"workflow_type":"STAR - Counts"},
       "cases":[{"submitter_id":"TCGA-AA-0001"}],
       "associated_entities":[{"entity_submitter_id":"TCGA-AA-0001-01A-11R"}]}
    b={**a,"file_id":"fileB"}
    norm={**a,"file_id":"normal","cases":[{"submitter_id":"TCGA-BB-0002"}],
          "associated_entities":[{"entity_submitter_id":"TCGA-BB-0002-11A-11R"}]}
    records,info=build([a,b,norm],{"TCGA-AA-0001","TCGA-BB-0002"})
    assert len(records)==3
    assert info["patients_with_multiple_tumor_rna_files"]==1
    assert info["patients_without_verified_file"]==1
    assert all(x["tumor_expression_matrix_eligible"]=="NOT_ASSESSED" for x in records)
    one,report=build([a],{"TCGA-AA-0001"})
    assert report["patients_with_one_tumor_rna_file"]==1
    assert one[0]["gdc_md5sum"]=="0"*32
    ids=candidates_from_mask_qc([{"patient_id":"TCGA-AA-0001",
                                  "nifti_mask_voxel_status":"PASS_NONEMPTY_NIFTI_MASK"}])
    assert ids=={"TCGA-AA-0001"}
    print("HCC_MRI_RNA_FILE_MANIFEST_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--input-dir",default="artifacts/hcc_mri")
    args=ap.parse_args()
    if args.offline_test:
        offline_test()
        return
    root=Path(args.input_dir)
    with (root/"tcga_liverhccseg_mri_mask_voxel_qc.csv").open(
            encoding="utf-8",newline="") as handle:
        ids=candidates_from_mask_qc(list(csv.DictReader(handle)))
    records,report=build(fetch_files(),ids)
    with (root/"tcga_liverhccseg_gdc_star_tumor_rna_manifest.csv").open(
            "w",encoding="utf-8",newline="") as out:
        writer=csv.DictWriter(out,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    (root/"tcga_liverhccseg_gdc_star_tumor_rna_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if report["patients_without_verified_file"]:
        raise SystemExit("Missing tumor RNA file for some mask patients; do not promote cohort")


if __name__=="__main__":
    main()
