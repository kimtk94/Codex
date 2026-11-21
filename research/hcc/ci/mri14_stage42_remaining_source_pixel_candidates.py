#!/usr/bin/env python3
"""HCC Stage42 original source pixel candidate search for frozen remaining 12.
Strictly imaging source evidence only. Never clinical tissue or treatment GO.
Uses the same Stage39 247 source geometries and Stage40 48x48 comparison.
"""
import argparse,csv,io,json,hashlib,os
from pathlib import Path
from collections import Counter
from zipfile import ZipFile
import numpy as np
import pydicom
from mri_mask_voxel_audit import HTTPRangeFile
from mri14_stage36_original_dicom_source_directory import ARCHIVE,cases
from mri14_stage39_original_pv_nifti_dicom_geometry import NIFTI_ARCHIVE
from mri14_stage40_source_dicom_pv_pixel_pattern_pilot import (
    PILOT,pv_pixels,members_in_directory,fractions,match_pixel_sample)
from fast_zip_member_range import get_member_with_ranges

REMAINING=tuple(sorted(set(cases())-set(PILOT)))
GEOM="MATRIX_SPACING_INSTANCE_COUNT_COMPATIBLE_NOT_IDENTITY"
STRONG="DESCRIPTIVE_STRONG_SOURCE_PIXEL_PATTERN_CANDIDATE_ONLY"
COLUMNS=("patient_id","source_directory","SeriesInstanceUID","SeriesDescription",
         "original_geometry_candidate","original_dicom_instances","source_samples_tested",
         "valid_original_dicom_samples","hold_original_dicom_samples",
         "minimum_abs_pearson","median_abs_pearson","max_abs_pearson",
         "matched_native_pv_z_indices","matched_inplane_transforms",
         "pixel_pattern_label","original_PV_exact_source_series_identity",
         "MRI_before_HCC_treatment","same_MRI_index_lesion_RNA",
         "clinical_eligible","biology_tests","claim_ceiling")

def check(p,message):
    if not p:raise ValueError(message)

def read(path):
    with Path(path).open(newline="",encoding="utf8") as f:
        return list(csv.DictReader(f))

def prepare(path,pid):
    check(pid in REMAINING and len(REMAINING)==12,"STAGE42_FIXED_TWELVE_CASES_DRIFT")
    allrows=read(path)
    check(len(allrows)==247 and len(set(r["patient_id"] for r in allrows))==14,
          "PINNED_STAGE39_247_SOURCE_HEADERS_DRIFT")
    check(all(r["clinical_eligible"]=="NOT_ASSESSED" and
              r["original_selected_PV_exact_DICOM_series_verified"]=="NOT_ASSESSED" and
              r["claim_ceiling"]=="S0" for r in allrows),"CLINICAL_PROMOTION_FORBIDDEN")
    return sorted([r for r in allrows if r["patient_id"]==pid and
                   r["source_geometry_evidence_class"]==GEOM],
                  key=lambda r:r["source_DICOM_directory"])

def evaluate(pid,candidate,z,nifti):
    path=candidate["source_DICOM_directory"]
    expected=candidate["source_DICOM_SeriesInstanceUID"]
    members=members_in_directory(z,pid,path)
    n=len(members)
    check(n==int(candidate["source_DICOM_series_instance_files"]),
          "ORIGINAL_DICOM_SOURCE_CANDIDATE_MEMBER_COUNT_CHANGED")
    vals=[];modes=[];zs=[];holds=[]
    for k in fractions(n):
        info=members[k]
        try:
            raw=get_member_with_ranges(ARCHIVE,info,z.fp.total)
            ds=pydicom.dcmread(io.BytesIO(raw))
            check(str(ds.PatientID).strip().upper().replace("_","-")==pid and
                  str(ds.Modality).upper()=="MR","ORIGINAL_PATIENT_OR_MODALITY_MISMATCH")
            check(str(ds.SeriesInstanceUID)==expected,
                  "ORIGINAL_SOURCE_DICOM_SERIES_UID_MISMATCH")
            arr=np.asarray(ds.pixel_array,dtype=np.float32)
            check(arr.ndim==2 and np.isfinite(arr).all(),"INVALID_DICOM_2D_PIXELS")
            slope=float(getattr(ds,"RescaleSlope",1.0))
            intercept=float(getattr(ds,"RescaleIntercept",0.0))
            res=match_pixel_sample(nifti,arr*slope+intercept)
            check(res is not None,"ORIGINAL_DICOM_SOURCE_CANNOT_PIXEL_COMPARE")
            cor,zidx,mode=res
            vals.append(abs(float(cor)));zs.append(int(zidx));modes.append(mode)
        except Exception as exc:
            holds.append(type(exc).__name__+":"+str(exc)[:120])
        print("HCC_STAGE42_ORIGINAL_SOURCE_SAMPLE",pid,info.filename,
              f"corr={vals[-1]:.7f}" if len(vals)+len(holds)==len(zs)+len(holds) and vals else "HOLD",
              flush=True)
    is_strong=(len(vals)==3 and min(vals)>=.995 and
               len(set(zs))==3 and len(set(modes))==1)
    return dict(patient_id=pid,source_directory=path,
      SeriesInstanceUID=expected,
      SeriesDescription=candidate["source_DICOM_SeriesDescription"],
      original_geometry_candidate="YES",original_dicom_instances=n,
      source_samples_tested=3,valid_original_dicom_samples=len(vals),
      hold_original_dicom_samples=len(holds),
      minimum_abs_pearson=f"{min(vals):.7f}" if vals else "",
      median_abs_pearson=f"{float(np.median(vals)):.7f}" if vals else "",
      max_abs_pearson=f"{max(vals):.7f}" if vals else "",
      matched_native_pv_z_indices="|".join(map(str,zs)),
      matched_inplane_transforms="|".join(modes),
      pixel_pattern_label=STRONG if is_strong else
        "DESCRIPTIVE_PIXEL_PATTERN_CANDIDATE_INCOMPLETE_OR_AMBIGUOUS",
      original_PV_exact_source_series_identity="NOT_ASSESSED",
      MRI_before_HCC_treatment="NOT_ASSESSED",
      same_MRI_index_lesion_RNA="NOT_ASSESSED",
      clinical_eligible="NOT_ASSESSED",biology_tests=0,claim_ceiling="S0")

def save_csv(path,rows):
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS);w.writeheader();w.writerows(rows)

def case_run(pid,manifest,out):
    cand=prepare(manifest,pid)
    check(len(cand)>=1,"STAGE42_NO_GEOMETRIC_SOURCE_CANDIDATE")
    with ZipFile(HTTPRangeFile(NIFTI_ARCHIVE)) as native:
        name,sha,pv=pv_pixels(native,pid)
    allrows=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as z:
        for i,r in enumerate(cand):
            res=evaluate(pid,r,z,pv)
            allrows.append(res)
            print("HCC_STAGE42_CANDIDATE_EVALUATED",pid,i+1,len(cand),
                  res["minimum_abs_pearson"],res["pixel_pattern_label"],flush=True)
    strong=[r for r in allrows if r["pixel_pattern_label"]==STRONG]
    decision=("ONE_UNIQUE_STRONG_PATTERN_CANDIDATE_FULL_STACK_REQUIRED" if len(strong)==1 else
              "HOLD_MULTIPLE_STRONG_SOURCE_SERIES" if len(strong)>1 else
              "HOLD_NO_STRONG_SOURCE_SERIES")
    summary=dict(
      stage="HCC_STAGE42_REMAINING_12_SOURCE_PIXEL_CANDIDATE",
      patient_id=pid,source_original_pv_nifti=name,
      original_pv_member_sha256=sha,source_candidate_geometry_series=len(cand),
      source_DICOM_sample_reads_attempted=len(allrows)*3,
      source_DICOM_sample_reads_valid=sum(int(r["valid_original_dicom_samples"]) for r in allrows),
      source_DICOM_sample_HOLD=sum(int(r["hold_original_dicom_samples"]) for r in allrows),
      strong_source_pixel_pattern_candidates=len(strong),
      source_pixel_pattern_decision=decision,
      unique_candidate_series_uid=strong[0]["SeriesInstanceUID"] if len(strong)==1 else "",
      unique_candidate_source_directory=strong[0]["source_directory"] if len(strong)==1 else "",
      exact_original_PV_NIfTI_DICOM_full3d_match_verified_n=0,
      independent_radiologist_approved_n=0,
      MRI_before_HCC_treatment_verified_n=0,
      RNA_is_same_MRI_index_tumor_verified_n=0,
      clinical_eligible_n="NOT_ASSESSED",MRI_RNA_biological_tests=0,
      claim_ceiling="S0")
    out.mkdir(parents=True,exist_ok=True)
    save_csv(out/"stage42_candidate_source_pixel_patterns.csv",allrows)
    (out/"stage42_patient_source_pixel_candidate_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    print("HCC_STAGE42_SOURCE_PATIENT_SUMMARY",json.dumps(summary,sort_keys=True),flush=True)

def aggregate(input_dir,out):
    from collections import Counter
    summaries=[];data=[]
    for pid in REMAINING:
        root=input_dir/("hcc-stage42-source-pixel-"+pid)
        j=root/"stage42_patient_source_pixel_candidate_summary.json"
        c=root/"stage42_candidate_source_pixel_patterns.csv"
        check(j.is_file() and c.is_file(),"STAGE42_MISSING_ONE_OF_TWELVE_SHARDS:"+pid)
        case=json.loads(j.read_text())
        check(case["patient_id"]==pid and case["clinical_eligible_n"]=="NOT_ASSESSED"
              and case["exact_original_PV_NIfTI_DICOM_full3d_match_verified_n"]==0 and
              case["MRI_RNA_biological_tests"]==0 and case["claim_ceiling"]=="S0",
              "STAGE42_UNSUPPORTED_CLINICAL_SOURCE_PROMOTION")
        rows=read(c)
        check(len(rows)==case["source_candidate_geometry_series"],
              "STAGE42_CASE_CANDIDATE_ROWS_MISMATCH")
        summaries.append(case);data.extend(rows)
    unique=[j for j in summaries if j["source_pixel_pattern_decision"]==
            "ONE_UNIQUE_STRONG_PATTERN_CANDIDATE_FULL_STACK_REQUIRED"]
    results=dict(stage="HCC_STAGE42_REMAINING_TWELVE_ORIGINAL_SOURCE_CANDIDATES",
      frozen_source_patient_denominator=14,stage41_3d_complete_n=2,
      stage42_patient_shards_completed=12,
      source_geometry_candidate_series_evaluated=len(data),
      total_original_DICOM_samples_attempted=sum(x["source_DICOM_sample_reads_attempted"] for x in summaries),
      total_original_DICOM_samples_valid=sum(x["source_DICOM_sample_reads_valid"] for x in summaries),
      source_patients_unique_strong_pixel_candidate=len(unique),
      source_patients_ambiguous_or_no_strong_candidate=12-len(unique),
      full3D_source_identity_newly_verified_n=0,
      overall_full3D_source_provenance_verified_n=2,
      clinical_eligible_n="NOT_ASSESSED",independent_radiologist_approved_n=0,
      same_index_tumor_RNA_verified_n=0,
      MRI_before_HCC_treatment_verified_n=0,
      MRI_RNA_biological_tests=0,claim_ceiling="S0",
      source_whole_Zenodo_ZIP_MD5_verified=False)
    out.mkdir(parents=True,exist_ok=True)
    save_csv(out/"stage42_all12_original_source_pixel_pattern_candidates.csv",data)
    (out/"stage42_12patient_original_source_candidate_summary.json").write_text(json.dumps(results,indent=2)+"\n")
    with (out/"stage42_12patient_source_priority.csv").open("w",newline="") as f:
        cols=["patient_id","source_candidate_geometry_series","strong_source_pixel_pattern_candidates",
              "source_pixel_pattern_decision","unique_candidate_series_uid",
              "unique_candidate_source_directory","clinical_eligible_n"]
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        w.writerows({c:x[c] for c in cols} for x in summaries)
    report="# HCC Stage42 original 12-patient DICOM pixel source candidate screen\n\n"+\
        json.dumps(results,indent=2)+"\n\nFull 3D source validation still required per unique case; clinical RNA and pretreatment HOLD.\n"
    (out/"stage42_candidate_screen_report.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE42_TWELVE_ORIGINAL_SOURCE_CANDIDATES_AGGREGATED",json.dumps(results,sort_keys=True),flush=True)

def offline():
    check(len(REMAINING)==12 and len(cases())==14,"STAGE42_FROZEN_CASES_CHANGED")
    check(STRONG.endswith("_CANDIDATE_ONLY"),"STAGE42_SOURCE_LABEL_CHANGED")
    print("HCC_STAGE42_TWELVE_FROZEN_CASES_AND_FAIL_CLOSED_SOURCE_FIXTURES_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--patient",choices=REMAINING)
    p.add_argument("--stage39-csv",type=Path)
    p.add_argument("--aggregate",action="store_true")
    p.add_argument("--shard-root",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage42"))
    p.add_argument("--offline-test",action="store_true")
    a=p.parse_args()
    offline()
    if a.offline_test:return
    if a.aggregate:
        check(a.shard_root is not None,"STAGE42_MISSING_SHARDS")
        aggregate(a.shard_root,a.out_dir)
    else:
        check(a.patient is not None and a.stage39_csv and a.stage39_csv.is_file(),
              "STAGE42_PINNED_STAGE39_SOURCE_MANIFEST_REQUIRED")
        case_run(a.patient,a.stage39_csv,a.out_dir)
if __name__=="__main__":main()
