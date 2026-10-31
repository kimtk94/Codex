#!/usr/bin/env python3
"""Patient barcode overlap across distinct TCGA-LIHC CT, MRI tumor masks, and RNA files.

This is patient-level metadata overlap, not scan-timing, tumor-lesion, or
cross-modality registration evidence.
"""
import argparse
import csv
import json
from pathlib import Path

def read(path, fields):
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(fields).issubset(reader.fieldnames):
            raise ValueError(f"Unexpected input schema {path}: {fields}")
        return list(reader)


def analyze(ct, mri):
    ct_by={r["patient_id"]:r for r in ct
           if r.get("rna_primary_tumor_file_linked")=="YES"}
    mri_by={r["patient_id"]:r for r in mri
            if r.get("nifti_mask_voxel_status")=="PASS_NONEMPTY_NIFTI_MASK"}
    ids=sorted(set(ct_by)&set(mri_by))
    out=[{
        "patient_id":pid,
        "ct_series_uid_review_candidate":ct_by[pid]["selected_ct_series_uid"],
        "ct_review_tier":ct_by[pid]["review_tier"],
        "mri_mask_nifti_file":mri_by[pid]["nifti_member_path"],
        "mri_mask_voxel_count":mri_by[pid]["mask_nonzero_voxels"],
        "ct_tumor_roi_status":"NOT_VERIFIED",
        "ct_mri_scan_temporal_comparability":"NOT_VERIFIED",
        "same_tumor_lesion_proof":"NOT_VERIFIED",
        "RNA_tumor_file_metadata":"LINKED",
        "eligible_ct_mri_rna_analysis":"NOT_ASSESSED",
    } for pid in ids]
    return out, {
        "status":"PASS_TRIPLE_MODALITY_BARCODE_METADATA_ONLY",
        "ct_rna_patient_candidates":len(ct_by),
        "mri_nonempty_tumor_mask_rna_patient_candidates":len(mri_by),
        "ct_mri_rna_patient_overlap":len(ids),
        "paired_ct_mri_lesion_cases_verified":"NOT_ASSESSED",
        "note":"Matching TCGA patient IDs does not prove CT and MRI show the same lesion or stage/timepoint.",
    }


def offline_test():
    ct=[{"patient_id":"TCGA-AA-0001","rna_primary_tumor_file_linked":"YES",
         "selected_ct_series_uid":"UID1","review_tier":"P2"}]
    mri=[{"patient_id":"TCGA-AA-0001","nifti_mask_voxel_status":"PASS_NONEMPTY_NIFTI_MASK",
          "nifti_member_path":"rater1_tumor1.nii.gz","mask_nonzero_voxels":"100"}]
    rows,summary=analyze(ct,mri)
    assert len(rows)==1 and summary["ct_mri_rna_patient_overlap"]==1
    assert rows[0]["eligible_ct_mri_rna_analysis"]=="NOT_ASSESSED"
    print("HCC_CT_MRI_RNA_TRIPLE_MODALITY_OFFLINE_TEST_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ct-dir",default="artifacts/hcc_tcia")
    ap.add_argument("--mri-dir",default="artifacts/hcc_mri")
    ap.add_argument("--output",default="artifacts/hcc_crossmodal")
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    if args.offline_test:
        offline_test()
        return
    ct=read(Path(args.ct_dir)/"tcga_hcc_same_series_review_queue.csv",
            ["patient_id","review_tier","selected_ct_series_uid","rna_primary_tumor_file_linked"])
    mri=read(Path(args.mri_dir)/"tcga_liverhccseg_mri_mask_voxel_qc.csv",
             ["patient_id","nifti_mask_voxel_status","nifti_member_path","mask_nonzero_voxels"])
    rows,summary=analyze(ct,mri)
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    columns=["patient_id","ct_series_uid_review_candidate","ct_review_tier",
             "mri_mask_nifti_file","mri_mask_voxel_count","ct_tumor_roi_status",
             "ct_mri_scan_temporal_comparability","same_tumor_lesion_proof",
             "RNA_tumor_file_metadata","eligible_ct_mri_rna_analysis"]
    with (out/"tcga_ct_mri_rna_triple_overlap.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    (out/"tcga_ct_mri_rna_triple_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
