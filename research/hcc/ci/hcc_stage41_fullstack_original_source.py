#!/usr/bin/env python3
"""Original HCC MRI PV NIfTI vs complete DICOM source stack audit, 2 fixed cases.
Technical image evidence only; no MRI treatment-episode or RNA tissue proof.
"""
import argparse,csv,hashlib,io,json,tempfile
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from hcc_stage41_fullstack_math import best_map,fullres_compare,coordinate_errors,offline_test
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from mri14_stage36_original_dicom_source_directory import ARCHIVE,patient,is_dicom_candidate,cases
from mri14_stage39_original_pv_nifti_dicom_geometry import NIFTI_ARCHIVE,source_pv
PILOT=("TCGA-BC-A3KG","TCGA-BC-A69I")
STRONG="DESCRIPTIVE_STRONG_SOURCE_PIXEL_PATTERN_CANDIDATE_ONLY"
def check(ok,msg):
    if not ok:raise ValueError(msg)
def choose(path,pid):
    with Path(path).open(newline="",encoding="utf8") as f:rows=list(csv.DictReader(f))
    check(len(rows)==8 and {r["patient_id"] for r in rows}==set(PILOT),"STAGE40_2_CASE_8_CANDIDATE_DRIFT")
    good=[r for r in rows if r["pixel_pattern_label"]==STRONG]
    check(len(good)==2 and {r["patient_id"] for r in good}==set(PILOT),
          "STAGE40_STRONG_SOURCE_SERIES_NOT_UNIQUE_PER_PATIENT")
    selected=next(r for r in good if r["patient_id"]==pid)
    check(selected["exact_PV_source_series_verified"]=="NOT_ASSESSED" and
          selected["clinical_eligible"]=="NOT_ASSESSED","STAGE40_CLINICAL_FALSE_PROMOTION")
    return selected
def get_pv(pid):
    import nibabel as nib
    with ZipFile(HTTPRangeFile(NIFTI_ARCHIVE)) as archive:
        filename,sha,shape,spacing=source_pv(archive,pid)
        data=get_member_with_ranges(NIFTI_ARCHIVE,archive.getinfo(filename),archive.fp.total)
    check(hashlib.sha256(data).hexdigest()==sha,"SOURCE_NATIVE_PV_CHANGED_AFTER_CRC")
    with tempfile.TemporaryDirectory(prefix="hcc41pv_") as t:
        f=Path(t)/"pv.nii.gz";f.write_bytes(data)
        im=nib.load(str(f))
        pv=np.asarray(im.get_fdata(dtype=np.float32),dtype=np.float32)
        affine=np.asarray(im.affine,dtype=np.float64)
    check(pv.shape==shape and np.isfinite(pv).all(),"NATIVE_PV_SOURCE_INVALID")
    check(np.isfinite(affine).all() and abs(np.linalg.det(affine[:3,:3]))>1e-7,
          "NATIVE_PV_AFFINE_DEGENERATE")
    return filename,sha,pv,affine
def original_stack(pid,directory,uid,expected):
    import pydicom
    with ZipFile(HTTPRangeFile(ARCHIVE)) as z:
        entries=sorted((x for x in z.infolist() if not x.is_dir() and
            patient(x.filename)==pid and str(Path(x.filename).parent)==directory and
            is_dicom_candidate(x.filename) and 132<=x.file_size<=24*1024*1024),
            key=lambda x:x.filename)
        check(len(entries)==expected,"SOURCE_DICOM_DIRECTORY_N_NOT_SAME_PV")
        rows=[]
        for i,entry in enumerate(entries):
            data=get_member_with_ranges(ARCHIVE,entry,z.fp.total)
            ds=pydicom.dcmread(io.BytesIO(data))
            check(str(ds.PatientID).strip().upper().replace("_","-")==pid,
                  "SOURCE_PATIENT_MISMATCH")
            check(str(ds.Modality).upper()=="MR" and str(ds.SeriesInstanceUID)==uid,
                  "SOURCE_SERIES_UID_OR_MODALITY_MISMATCH")
            im=np.asarray(ds.pixel_array,dtype=np.float32)
            check(im.ndim==2 and np.isfinite(im).all(),"ORIGINAL_DICOM_NOT_SINGLE_2D")
            slope=float(getattr(ds,"RescaleSlope",1.0))
            intercept=float(getattr(ds,"RescaleIntercept",0.0))
            iop=np.asarray(ds.ImageOrientationPatient,dtype=np.float64)
            ipp=np.asarray(ds.ImagePositionPatient,dtype=np.float64)
            spacing=np.asarray(ds.PixelSpacing,dtype=np.float64)
            check(np.isfinite(slope) and np.isfinite(intercept) and
                  iop.shape==(6,) and ipp.shape==(3,) and spacing.shape==(2,),
                  "ORIGINAL_DICOM_PHYSICAL_TAG_INVALID")
            check(np.isfinite(iop).all() and np.isfinite(ipp).all() and
                  np.isfinite(spacing).all(),"ORIGINAL_DICOM_PHYSICAL_TAG_NONFINITE")
            rows.append(dict(pixels=im*slope+intercept,iop=iop,ipp=ipp,
                             spacing=spacing,sop=str(ds.SOPInstanceUID),
                             study=str(ds.StudyInstanceUID),sha256=hashlib.sha256(data).hexdigest()))
            if (i+1)%16==0 or i+1==len(entries):
                print("HCC_STAGE41_ORIGINAL_SOURCE_SLICES_READ",pid,i+1,len(entries),flush=True)
    check(len({r["sop"] for r in rows})==expected,"SOURCE_SOP_NOT_UNIQUE")
    check(len({r["study"] for r in rows})==1,"SOURCE_STUDY_MIXED")
    iop=rows[0]["iop"];spacing=rows[0]["spacing"]
    check(all(np.max(np.abs(r["iop"]-iop))<2e-4 and
              np.max(np.abs(r["spacing"]-spacing))<1e-3 for r in rows),
          "ORIGINAL_DICOM_ORIENTATION_OR_SPACING_INCONSISTENT")
    normal=np.cross(iop[:3],iop[3:])
    check(np.linalg.norm(normal)>0.9,"ORIGINAL_DICOM_NORMAL_DEGENERATE")
    normal/=np.linalg.norm(normal)
    rows.sort(key=lambda r:float(r["ipp"]@normal))
    positions=np.array([float(r["ipp"]@normal) for r in rows])
    diffs=np.diff(positions)
    check(len(diffs)>0 and np.min(diffs)>0.05 and
          np.max(np.abs(diffs-np.median(diffs)))<0.5,
          "DICOM_PHYSICAL_SLICE_POSITIONS_INCONSISTENT")
    return rows,float(np.median(diffs))
def run(pid,source,out):
    check(pid in PILOT and len(cases())==14,"FROZEN_14_CASE_SCOPE_CHANGED")
    selected=choose(source,pid)
    filename,sha,pv,affine=get_pv(pid)
    stack,step=original_stack(pid,selected["source_directory"],
                              selected["SeriesInstanceUID"],pv.shape[2])
    mapping=best_map(pv,stack)
    rows=fullres_compare(pv,stack,mapping)
    world=coordinate_errors(pv,affine,stack,mapping)
    good=[r for r in rows if r["pearson"] is not None]
    strong=(len(good)==len(rows) and
            min(r["pearson"] for r in good)>.9999 and
            max(r["normalized_linear_fit_rmse"] for r in good)<.016 and
            mapping["criterion"][1]>.9999 and max(world)<2.0)
    status=("STRONG_FULL_3D_PIXELS_AND_LPS_RAS_AFFINE_TECHNICAL_MATCH" if strong
            else "HOLD_PIXEL_OR_AFFINE_SOURCE_MISMATCH")
    summary=dict(stage="HCC_STAGE41_COMPLETE_ORIGINAL_DICOM_PV_SOURCE_VOLUME",
       patient_id=pid,source_pv_nifti_path=filename,source_pv_sha256=sha,
       source_dicom_directory=selected["source_directory"],
       source_dicom_series_uid=selected["SeriesInstanceUID"],
       native_PV_shape_xyz=list(pv.shape),
       original_DICOM_CRC_verified_instances=len(stack),
       original_DICOM_unique_SOP_instances=len({r["sop"] for r in stack}),
       full_resolution_slices_compared=len(good),physical_DICOM_slice_spacing_mm=step,
       inplane_transform=str(mapping["mode"]),reverse_z=mapping["reverse"],
       grid_min_pearson=mapping["criterion"][1],
       fullres_min_pearson=min((r["pearson"] for r in good),default=None),
       fullres_median_pearson=float(np.median([r["pearson"] for r in good])) if good else None,
       fullres_max_normalized_rmse=max((r["normalized_linear_fit_rmse"] for r in good),default=None),
       maximum_LPS_RAS_physical_coordinate_error_mm=max(world),
       technical_source_imaging_verdict=status,
       bitwise_pixel_equality_not_proven=True,whole_source_ZIP_MD5_not_recomputed=True,
       independent_radiologist_review="NOT_ASSESSED",
       original_MRI_before_HCC_treatment_episode="NOT_ASSESSED",
       original_RNA_same_imaged_index_lesion="NOT_ASSESSED",
       clinical_eligible="NOT_ASSESSED",MRI_RNA_biology_tests=0,claim_ceiling="S0")
    out.mkdir(parents=True,exist_ok=True)
    (out/"stage41_full_source_DICOM_PV_3d_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    with (out/"stage41_original_all_DICOM_slice_fullresolution.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (out/"stage41_original_source_3d_report.md").write_text(
        "# Stage41 original source 3D pixel/coordinate assessment\n\n"+
        json.dumps(summary,indent=2)+"\n")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
            f.write("# HCC Stage41 "+pid+"\n\nSource technical verdict "+status+
                    "\n\nClinical eligibility NOT_ASSESSED; biology 0/12 S0.\n")
    print("HCC_STAGE41_REAL_COMPLETE_SOURCE_STACK_RESULT",json.dumps(summary,sort_keys=True),flush=True)
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--offline-test",action="store_true")
    a.add_argument("--patient",choices=PILOT)
    a.add_argument("--stage40-csv",type=Path)
    a.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage41_source_fullstack"))
    x=a.parse_args()
    offline_test()
    if x.offline_test:return
    check(x.patient and x.stage40_csv and x.stage40_csv.is_file(),"VERIFIED_STAGE40_SOURCE_REQUIRED")
    run(x.patient,x.stage40_csv,x.out_dir)
if __name__=="__main__":main()
