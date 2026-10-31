#!/usr/bin/env python3
"""Read original LiverHccSeg publication XLSX metadata for 14 frozen HCC MRI cases.

Two small official Zenodo v1.1 XLSX workbooks, checksum-verified:
- LiverHccSeg_MetaData.xlsx (MR DICOM header metadata / published reading)
- segm_metrics.xlsx (published two-rater tumor segmentation metrics)

This audit may confirm the authors' expert readings existed and selected case
identifiers occur in the primary publications; it does NOT establish that an
independent local reviewer approved our selected ROI, original acquisition
predates all interventions, or that MRI lesion = RNA sample lesion.

Never subtract TCIA shifted dates from GDC diagnosis-relative date offsets.
"""
import argparse,csv,json,re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from liverhccseg_mri_rna_audit import BARCODE,FILES,fetch_workbook,scan_book
from mri_parallel_batch_gate import load,ROI

OUT=("patient_id","selected_index_tumor_number","official_mri_metadata_rows",
     "official_hcc_segmentation_metrics_rows",
     "official_published_hcc_dice_present",
     "official_expert_readers_in_publication",
     "published_cohort_pretreatment_scan_priority",
     "patient_specific_pretreatment_mri_verified",
     "selected_roi_expert_review_reconfirmed",
     "mri_to_exact_rna_lesion_match",
     "clinical_eligibility")

def extract_mention_count(wb,filename,ids):
    counts,_tabs,seg_ids=scan_book(wb,filename)
    return {pid:counts.get(pid,0) for pid in ids},set(seg_ids)

def audit(mri,segment,metric_ids,source):
    if set(mri)!=set(source) or set(segment)!=set(source):
        raise ValueError("Case-level official meta IDs differ from frozen 14")
    rows=[]
    for pid in sorted(source):
        if mri[pid]<=0:
            raise ValueError(f"Official MRI metadata missing: {pid}")
        if segment[pid]<=0 or pid not in metric_ids:
            raise ValueError(f"Official tumor annotation reader metric missing: {pid}")
        r=source[pid]
        if r["expert_review"]!="NOT_ASSESSED" or r["pretreatment_verified"]!="NOT_ASSESSED":
            raise ValueError("Frozen local image/treatment eligibility secretly changed")
        rows.append({
           "patient_id":pid,
           "selected_index_tumor_number":r["representative_tumor_number"],
           "official_mri_metadata_rows":mri[pid],
           "official_hcc_segmentation_metrics_rows":segment[pid],
           "official_published_hcc_dice_present":"YES",
           "official_expert_readers_in_publication":"TWO_BOARD_CERTIFIED_ABDOMINAL_RADIOLOGISTS_SOURCE_DATASET",
           "published_cohort_pretreatment_scan_priority":"PREFERRED_WHEN_MULTIPLE_STUDIES_PUBLISHED_PROTOCOL",
           "patient_specific_pretreatment_mri_verified":"NOT_VERIFIED",
           "selected_roi_expert_review_reconfirmed":"NOT_ASSESSED",
           "mri_to_exact_rna_lesion_match":"NOT_VERIFIED",
           "clinical_eligibility":"HOLD_UNRESOLVED_NOT_EXCLUDED",
        })
    return rows

def offline_test():
    s=load(ROI)
    a={pid:2 for pid in s}
    b={pid:1 for pid in s}
    rows=audit(a,b,set(s),s)
    assert len(rows)==14
    assert all(r["official_published_hcc_dice_present"]=="YES" for r in rows)
    assert all(r["patient_specific_pretreatment_mri_verified"]=="NOT_VERIFIED" for r in rows)
    del a["TCGA-BC-A10Y"]
    try:audit(a,b,set(s),s)
    except ValueError:pass
    else:raise AssertionError("Missing source MRI patient improperly accepted")
    print("HCC_LIVERHCCSEG_OFFICIAL_PUBLICATION_EVIDENCE_OFFLINE_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--out-dir",default="artifacts/hcc_batch_publication")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    frozen=load(ROI)
    observed={}
    verified={}
    metric_ids=set()
    for filename,md5 in FILES.items():
        wb,digest,nbytes=fetch_workbook(filename,md5)
        try:
            source,tabs,segids=scan_book(wb,filename)
            observed[filename]={pid:source.get(pid,0) for pid in frozen}
            if filename=="segm_metrics.xlsx":
                metric_ids=set(segids)
            verified[filename]={
                "md5":digest,"nbytes":nbytes,
                "all_tcga_ids_in_workbook":len(source),
                "sheet_headers":[{"sheet":x["sheet"],"rows":x["rows"],
                                  "headers":x["headers"][:20]} for x in tabs]
            }
        finally:
            wb.close()
    rows=audit(observed["LiverHccSeg_MetaData.xlsx"],
               observed["segm_metrics.xlsx"],metric_ids,frozen)
    root=Path(args.out_dir);root.mkdir(parents=True,exist_ok=True)
    with (root/"hcc_mri14_published_expert_reader_metadata_crosswalk.csv").open(
        "w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=OUT)
        w.writeheader();w.writerows(rows)
    summary={
       "status":"PASS_OFFICIAL_EXPERT_SEGMENTATION_PUBLICATION_METADATA",
       "checked_utc":datetime.now(timezone.utc).isoformat(),
       "source_article_doi":"10.1016/j.dib.2023.109662",
       "source_version":"zenodo_8179129_v1.1",
       "official_workbook_hashes":verified,
       "n_frozen_cases":14,
       "mri_metadata_present_cases":sum(r["official_mri_metadata_rows"]>0 for r in rows),
       "published_hcc_reader_metric_present_cases":sum(r["official_published_hcc_dice_present"]=="YES" for r in rows),
       "published_expert_reader_status":"TWO_BOARD_CERTIFIED_ABDOMINAL_RADIOLOGISTS_SOURCE_ANNOTATION",
       "published_scan_selection_protocol":"PRETREATMENT_SCANS_PREFERRED_WHEN_MULTIPLE_AVAILABLE",
       "verified_patient_specific_pretreatment_mri":"NOT_VERIFIED",
       "independently_reconfirmed_selected_index_lesion":"NOT_ASSESSED",
       "same_selected_mri_lesion_as_rna_sample":"NOT_VERIFIED",
       "qualified_paired_patients":"NOT_ASSESSED",
       "association_tests_performed":False,
       "claim_ceiling":"S0",
       "note":"Dataset radiologists annotated the source cohort; independent case-level ROI re-review, therapy timing and matched resected lesion remain unresolved."
    }
    (root/"hcc_mri14_published_source_evidence_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="official_workbook_hashes"},ensure_ascii=False))

if __name__=="__main__":
    main()
