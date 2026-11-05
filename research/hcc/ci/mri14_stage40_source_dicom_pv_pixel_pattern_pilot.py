#!/usr/bin/env python3
"""HCC Stage40 original source DICOM↔native PV NIfTI *pixel pattern* pilot.

Predefined cases TCGA-BC-A3KG and TCGA-BC-A69I. Read frozen Stage39
three-way geometry candidates (4 each), original PV NIfTI, and 3 DICOM
instances from each candidate folder (20%,50%,80% source filename order).
Compute highest 2D Pearson across every PV z-slice and 8 in-plane
transpose/reflection transforms on a fixed 48x48 grid. Actual slice
matches are candidates, never unqualified exact source-series identity.
No outcome or RNA data used for selecting MRI sources, and no original
DICOM acquisition date is compared to GDC diagnosis-relative dates.

A high correlation does NOT demonstrate full pixel-array equality,
affine alignment, same imaged lesion/RNA tumor tissue, treatment-naivety,
or clinical/biological eligibility.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from collections import Counter,defaultdict
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from mri14_stage36_original_dicom_source_directory import (
    ARCHIVE,patient,is_dicom_candidate,cases)
from mri14_stage39_original_pv_nifti_dicom_geometry import (
    NIFTI_ARCHIVE,source_pv)

PILOT=("TCGA-BC-A3KG","TCGA-BC-A69I")
GRID=48
SAMPLE_FRACTIONS=(.2,.5,.8)
SAMPLE_COLS=("patient_id","source_directory","SeriesInstanceUID",
 "SeriesDescription","geometry_class","candidate_dicom_instances_in_folder",
 "sample_fraction","sample_filename","sample_SOPInstanceUID","member_sha256",
 "source_DICOM_crc_verified","source_DICOM_PatientID_checked",
 "source_DICOM_series_UID_checked","source_DICOM_image_shape",
 "PV_NIfTI_member","PV_NIfTI_member_sha256","PV_NIfTI_shape",
 "compared_PV_slices","best_PV_slice_index","best_inplane_transform",
 "max_abs_Pearson","signed_Pearson_at_max_abs","sample_status",
 "selected_PV_exact_source_identity","MRI_pre_HCC_treatment",
 "same_MRI_index_lesion_GDC_RNA","clinical_eligible","biology_tests","claim_ceiling")
GROUP_COLS=("patient_id","source_directory","SeriesInstanceUID",
 "geometry_class","source_DICOM_series_valid_samples",
 "sample_count","source_sample_HOLD_count","median_abs_Pearson",
 "min_abs_Pearson","max_abs_Pearson","matched_PV_z_indices",
 "matched_PV_slice_unique_count","best_inplane_transform_consensus",
 "pixel_pattern_label","exact_PV_source_series_verified",
 "clinical_eligible","biology_tests","claim_ceiling")

def check(ok,msg):
    if not ok:raise ValueError(msg)

def load(path):
    with open(path,newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def pilot_manifest(path):
    rows=load(path)
    check(len(rows)==247 and len({r["patient_id"] for r in rows})==14,
          "STAGE39_ORIGINAL_SOURCE_247_HEADER_UNIVERSE_CHANGED")
    selected=defaultdict(list)
    for r in rows:
        check(r["clinical_eligible"]=="NOT_ASSESSED" and
              r["original_selected_PV_exact_DICOM_series_verified"]=="NOT_ASSESSED" and
              r["claim_ceiling"]=="S0","SOURCE_39_CLINICAL_GATE_CHANGED")
        if r["patient_id"] in PILOT and r["source_geometry_evidence_class"]==\
                "MATRIX_SPACING_INSTANCE_COUNT_COMPATIBLE_NOT_IDENTITY":
            selected[r["patient_id"]].append(r)
    check(set(selected)==set(PILOT),"STAGE40_PILOT_FROZEN_CANDIDATE_CASES_MISSING")
    for p in PILOT:
        check(len(selected[p])==4,"STAGE40_SOURCE_4_CANDIDATE_GEOMETRY_DRIFT:"+p)
        check(len({r["source_DICOM_directory"] for r in selected[p]})==4,
              "DUPLICATE_SOURCE_DIRECTORY_CANDIDATE")
    return selected

def pv_pixels(z,pid):
    import nibabel as nib
    # Stage39 source_pv verifies official member CRC, gzip NIfTI header,
    # source SHA256, and patient filename. Reopen only the chosen source
    # member for actual image voxel values.
    path,digest,shape,spacing=source_pv(z,pid)
    info=z.getinfo(path)
    blob=get_member_with_ranges(NIFTI_ARCHIVE,info,z.fp.total)
    check(hashlib.sha256(blob).hexdigest()==digest,
          "SOURCE_PV_NIFTI_CHANGED_BETWEEN_TWO_CRC_FETCHES")
    with tempfile.TemporaryDirectory(prefix="hcc40_srcpv_") as root:
        f=Path(root)/"pv.nii.gz";f.write_bytes(blob)
        im=nib.load(str(f))
        pix=np.asarray(im.get_fdata(dtype=np.float32),dtype=np.float32)
    check(tuple(pix.shape)==tuple(shape) and pix.ndim==3,"PV_SOURCE_NIFTI_VOLUME_CHANGED")
    check(np.isfinite(pix).all(),"PV_NIFTI_CONTAINS_NONFINITE_PIXEL_VALUES")
    return path,digest,pix

def normalized_pv(pixel):
    h,w,s=pixel.shape
    iy=np.linspace(0,h-1,GRID).astype(np.int64)
    ix=np.linspace(0,w-1,GRID).astype(np.int64)
    sampled=pixel[iy[:,None],ix[None,:],:].reshape(GRID*GRID,s).T
    sampled=sampled.astype(np.float32)
    sampled-=np.mean(sampled,axis=1,keepdims=True)
    norms=np.linalg.norm(sampled,axis=1)
    sampled/=np.maximum(norms[:,None],1e-10)
    return sampled,norms

def transforms(image, target_shape):
    for transpose in (False,True):
        base=image.T if transpose else image
        for flip0 in (False,True):
            for flip1 in (False,True):
                img=base
                if flip0:img=img[::-1,:]
                if flip1:img=img[:,::-1]
                if img.shape==target_shape:
                    yield ("transpose" if transpose else "native") + \
                        ("_flip0" if flip0 else "") + ("_flip1" if flip1 else ""),img

def match_pixel_sample(pv,orig):
    check(orig.ndim==2 and pv.ndim==3,"DICOM_2D_OR_PV_3D_REQUIRED")
    volume,norm=normalized_pv(pv)
    h,w,s=pv.shape
    iy=np.linspace(0,h-1,GRID).astype(np.int64)
    ix=np.linspace(0,w-1,GRID).astype(np.int64)
    max_result=None
    for mode,img in transforms(np.asarray(orig,dtype=np.float32),(h,w)):
        small=img[iy[:,None],ix[None,:]].reshape(GRID*GRID)
        if not np.isfinite(small).all():continue
        small=small-small.mean()
        sd=float(np.linalg.norm(small))
        if sd<=1e-10:continue
        small/=sd
        corrs=volume@small
        corrs[norm<=1e-10]=0
        ixbest=int(np.argmax(np.abs(corrs)))
        corr=float(np.clip(corrs[ixbest],-1.0,1.0))
        if max_result is None or abs(corr)>abs(max_result[0]):
            max_result=(corr,ixbest,mode)
    if max_result is None:return None
    return max_result

def members_in_directory(z,pid,directory):
    out=sorted([i for i in z.infolist()
        if not i.is_dir() and patient(i.filename)==pid and
        str(Path(i.filename).parent)==directory and
        is_dicom_candidate(i.filename) and 132<=i.file_size<=24*1024*1024],
        key=lambda i:i.filename)
    check(out,"SOURCE_CANDIDATE_DIRECTORY_HAS_NO_BOUNDED_DICOM_FILES")
    return out

def fractions(n):
    check(n>=3,"NEED_3_DICOM_SAMPLES_FOR_PILOT_SERIES")
    ans=[min(n-1,int(round((n-1)*f))) for f in SAMPLE_FRACTIONS]
    check(len(set(ans))==3,"DICOM_SELECTED_SAMPLE_INDICES_NOT_INDEPENDENT")
    return ans

def audit(pinned):
    import pydicom
    selected=pilot_manifest(pinned)
    from collections import defaultdict
    rows=[]
    with ZipFile(HTTPRangeFile(NIFTI_ARCHIVE)) as source:
        with ZipFile(HTTPRangeFile(ARCHIVE)) as z:
            for pid in PILOT:
                pvname,pvsha,pv=pv_pixels(source,pid)
                print("HCC_STAGE40_PV_ORIGINAL_PIXELS_VERIFIED",pid,pv.shape,pvname,flush=True)
                for candidate in selected[pid]:
                    directory=candidate["source_DICOM_directory"]
                    items=members_in_directory(z,pid,directory)
                    for frac,k in zip(SAMPLE_FRACTIONS,fractions(len(items))):
                        info=items[k]
                        row={key:"" for key in SAMPLE_COLS}
                        row.update({
                          "patient_id":pid,"source_directory":directory,
                          "SeriesInstanceUID":candidate["source_DICOM_SeriesInstanceUID"],
                          "SeriesDescription":candidate["source_DICOM_SeriesDescription"],
                          "geometry_class":candidate["source_geometry_evidence_class"],
                          "candidate_dicom_instances_in_folder":len(items),
                          "sample_fraction":frac,
                          "sample_filename":info.filename,
                          "source_DICOM_crc_verified":"NO",
                          "source_DICOM_PatientID_checked":"NO",
                          "source_DICOM_series_UID_checked":"NO",
                          "PV_NIfTI_member":pvname,
                          "PV_NIfTI_member_sha256":pvsha,
                          "PV_NIfTI_shape":"x".join(map(str,pv.shape)),
                          "compared_PV_slices":pv.shape[2],
                          "selected_PV_exact_source_identity":"NOT_ASSESSED",
                          "MRI_pre_HCC_treatment":"NOT_ASSESSED",
                          "same_MRI_index_lesion_GDC_RNA":"NOT_ASSESSED",
                          "clinical_eligible":"NOT_ASSESSED",
                          "biology_tests":0,"claim_ceiling":"S0"})
                        try:
                            buf=get_member_with_ranges(ARCHIVE,info,z.fp.total)
                            row["source_DICOM_crc_verified"]="YES"
                            row["member_sha256"]=hashlib.sha256(buf).hexdigest()
                            ds=pydicom.dcmread(io.BytesIO(buf))
                            patientok=str(ds.PatientID).strip().upper().replace("_","-")==pid
                            seriesok=str(ds.SeriesInstanceUID)==row["SeriesInstanceUID"]
                            row["source_DICOM_PatientID_checked"]="YES" if patientok else "NO"
                            row["source_DICOM_series_UID_checked"]="YES" if seriesok else "NO"
                            row["sample_SOPInstanceUID"]=str(ds.SOPInstanceUID)
                            check(patientok and seriesok,
                                  "SOURCE_DICOM_PATIENT_OR_SERIES_UID_MISMATCH")
                            check(str(ds.Modality)=="MR","SOURCE_NOT_MR")
                            img=np.asarray(ds.pixel_array,dtype=np.float32)
                            check(img.ndim==2,"MULTIFRAME_NOT_IMPLEMENTED")
                            row["source_DICOM_image_shape"]="x".join(map(str,img.shape))
                            m=match_pixel_sample(pv,img)
                            if m is None:
                                row["sample_status"]="HOLD_DIMENSION_OR_LOW_VARIANCE"
                            else:
                                corr,zbest,mode=m
                                row["best_PV_slice_index"]=zbest
                                row["best_inplane_transform"]=mode
                                row["max_abs_Pearson"]=f"{abs(corr):.7f}"
                                row["signed_Pearson_at_max_abs"]=f"{corr:.7f}"
                                row["sample_status"]="PASS_PIXEL_PATTERN_SCORE_ONLY"
                        except Exception as ex:
                            row["sample_status"]="HOLD_"+type(ex).__name__+":"+str(ex)[:150]
                        rows.append(row)
                        print("HCC_STAGE40_DICOM_PIXEL_COMPARE",pid,
                              row["sample_status"],
                              row.get("max_abs_Pearson","-"),
                              row.get("best_PV_slice_index","-"),
                              flush=True)
    return rows

def report(rows,out):
    groups=defaultdict(list)
    for r in rows:groups[(r["patient_id"],r["source_directory"])].append(r)
    check(len(rows)==24 and len(groups)==8,
          "STAGE40_PILOT_2_PATIENT_8_SERIES_24_SOURCE_SAMPLES_CHANGED")
    import statistics
    by=[]
    for (pid,folder),rs in sorted(groups.items()):
        vals=[float(r["max_abs_Pearson"]) for r in rs
              if r["sample_status"]=="PASS_PIXEL_PATTERN_SCORE_ONLY"]
        good=[r for r in rs if r["sample_status"]=="PASS_PIXEL_PATTERN_SCORE_ONLY"]
        modes=Counter(r["best_inplane_transform"] for r in good)
        zs={r["best_PV_slice_index"] for r in good}
        # A candidate remains ambiguous even if it exhibits a strong
        # pattern: no 3D registered full-image pixel equivalence performed.
        status=("DESCRIPTIVE_STRONG_SOURCE_PIXEL_PATTERN_CANDIDATE_ONLY"
                if len(vals)==3 and min(vals)>=0.995 and len(zs)==3
                and modes.most_common(1)[0][1]==3 else
                "DESCRIPTIVE_PIXEL_PATTERN_CANDIDATE_INCOMPLETE_OR_AMBIGUOUS")
        by.append({
           "patient_id":pid,"source_directory":folder,
           "SeriesInstanceUID":rs[0]["SeriesInstanceUID"],
           "geometry_class":rs[0]["geometry_class"],
           "source_DICOM_series_valid_samples":len(good),
           "sample_count":len(rs),"source_sample_HOLD_count":3-len(good),
           "median_abs_Pearson":f"{statistics.median(vals):.7f}" if vals else "",
           "min_abs_Pearson":f"{min(vals):.7f}" if vals else "",
           "max_abs_Pearson":f"{max(vals):.7f}" if vals else "",
           "matched_PV_z_indices":"|".join(sorted(str(z) for z in zs)),
           "matched_PV_slice_unique_count":len(zs),
           "best_inplane_transform_consensus":modes.most_common(1)[0][0]
              if modes and modes.most_common(1)[0][1]==3 else "NOT_UNIQUE",
           "pixel_pattern_label":status,
           "exact_PV_source_series_verified":"NOT_ASSESSED",
           "clinical_eligible":"NOT_ASSESSED",
           "biology_tests":0,"claim_ceiling":"S0"})
    summ={
      "stage":"HCC_STAGE40_ORIGINAL_PV_NIFTI_VS_DICOM_2CASE_8SERIES_PIXEL_PATTERN_PILOT",
      "pilot_patients":list(PILOT),
      "original_PV_source_NIfTI_voxel_volumes_verified":2,
      "source_threeway_geometry_candidate_series_tested":8,
      "source_DICOM_sample_instances_attempted":len(rows),
      "source_DICOM_pixel_pattern_comparisons_valid":
          sum(r["sample_status"]=="PASS_PIXEL_PATTERN_SCORE_ONLY" for r in rows),
      "source_DICOM_sample_HOLD_n":
          sum(r["sample_status"]!="PASS_PIXEL_PATTERN_SCORE_ONLY" for r in rows),
      "source_candidate_series_with_three_usable_samples":
          sum(int(r["source_DICOM_series_valid_samples"])==3 for r in by),
      "source_strong_pattern_candidate_series":
          sum(r["pixel_pattern_label"]==
          "DESCRIPTIVE_STRONG_SOURCE_PIXEL_PATTERN_CANDIDATE_ONLY" for r in by),
      "PV_source_to_DICOM_exact_registered_pixel_identity_verified_n":0,
      "MRI_before_HCC_treatment_verified_n":0,
      "RNA_from_same_selected_MRI_index_lesion_verified_n":0,
      "independent_radiologist_review_approved_n":0,
      "clinical_eligible_n":"NOT_ASSESSED",
      "MRI_RNA_biology_tests":0,
      "claim_ceiling":"S0",
      "full_original_Zenodo_archives_MD5_independently_verified":False,
      "pixel_similarity_not_physical_source_image_equality":True,
      "decision":"PIXEL_PATTERN_PILOT_COMPLETED_EXACT_PV_SOURCE_IDENTITY_HOLD"}
    out.mkdir(parents=True,exist_ok=True)
    def write(path,fieldnames,data):
        with (out/path).open("w",newline="",encoding="utf8") as f:
            w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(data)
    write("stage40_24_original_DICOM_PV_NIfTI_slice_correlations.csv",SAMPLE_COLS,rows)
    write("stage40_8_source_candidate_series_pixel_pattern_summary.csv",GROUP_COLS,by)
    (out/"stage40_two_case_original_pixel_pattern_summary.json").write_text(
        json.dumps(summ,indent=2)+"\n",encoding="utf8")
    lines=["# Stage40 official original source DICOM-vs-PV-NIfTI pixel pattern pilot",
      "", "Pilot cases TCGA-BC-A3KG, TCGA-BC-A69I.",
      "Four frozen Stage39 three-way geometry candidate source series per patient; three source DICOM samples per series.",
      "Pixel pattern comparison: best Pearson among 8 in-plane transformations and all native PV NIfTI z slices, at fixed 48x48 grid.",
      "Original source DICOM sample valid scores: "+
        str(summ["source_DICOM_pixel_pattern_comparisons_valid"])+"/24.",
      "Strong descriptive series candidates: "+
        str(summ["source_strong_pattern_candidate_series"])+"/8.",
      "No full volume-pixel equality, affine registration, source selection, expert adjudication, scan-treatment timing, or RNA tumor specimen provenance proved.",
      "Clinical eligible N NOT_ASSESSED, 0/12 tests, S0.","",
      "| Patient | Source series UID | Valid samples | Median absolute Pearson | Pattern label |",
      "|---|---|---:|---:|---|"]
    for r in by:
        lines.append("| "+r["patient_id"]+" | "+r["SeriesInstanceUID"]+" | "+
          str(r["source_DICOM_series_valid_samples"])+" | "+
          str(r["median_abs_Pearson"])+" | "+r["pixel_pattern_label"]+" |")
    result="\n".join(lines)+"\n"
    (out/"stage40_two_case_original_pixel_pattern_report.md").write_text(result)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(result)
    print("HCC_STAGE40_SOURCE_PIXEL_PATTERN_PILOT",json.dumps(summ,sort_keys=True),flush=True)

def offline():
    p=np.zeros((16,12,7),dtype=np.float32)
    for z in range(7):
        yy,xx=np.mgrid[:16,:12]
        p[:,:,z]=yy*2 + xx*3+z*(yy*xx+1)
    # 48-point grid with duplicates still deterministic.
    target=p[:,:,4].T[::-1,:]
    m=match_pixel_sample(p,target)
    check(m is not None and abs(m[0])>.9999 and m[1]==4,"TRUE_SOURCE_PIXEL_MATCH_FIXTURE")
    noise=np.ones((16,12),dtype=np.float32)
    check(match_pixel_sample(p,noise) is None,"CONSTANT_ORIGINAL_SOURCE_PIXEL_REJECT")
    check(len(cases())==14,"FROZEN_14_SOURCE_ROSTER")
    print("HCC_STAGE40_EIGHT_ORIENTATION_PEARSON_TRUE_MATCH_AND_NEGATIVE_FIXTURES_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage39-csv",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage40_pixel_pattern_pilot"))
    p.add_argument("--offline-test",action="store_true")
    x=p.parse_args()
    offline()
    if x.offline_test:return
    check(x.stage39_csv is not None and x.stage39_csv.is_file(),
          "SOURCE_STAGE39_VERIFIED_CSV_REQUIRED")
    report(audit(x.stage39_csv),x.out_dir)
if __name__=="__main__":main()
