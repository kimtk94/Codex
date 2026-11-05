#!/usr/bin/env python3
"""OpenSwissHCC v2 real independent HCC venous MRI-only source cohort pilot.

Frozen 59 independent subjects, 1 source-size-preselected HCC index lesion
each, 90 source-verified masks total. Use range HTTP access to only required
official NIfTI files within two multi-GB Zenodo subject ZIPs plus original
derivatives.zip. No full patient archive download and no biological data.

Incomplete geometry, missing image or too-small ROI are explicit HOLD records,
never silent patient exclusion nor automatic technical acceptance.
"""
import argparse,csv,hashlib,io,json,math,re,tempfile,zipfile
from collections import Counter
from pathlib import Path
from importlib.metadata import version

from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from mri_pv_pixel_overlay_audit import corner_offset_mm
from mri_pv_glcm_binwidth_spacing_factorial import make_extractor,FEATURE_KEYS

REC="https://zenodo.org/records/21992461"
IMG_GROUPS=((44,REC+"/files/sub-001-sub-044.zip?download=1"),
            (88,REC+"/files/sub-044-sub-088.zip?download=1"),
            (132,REC+"/files/sub-088-sub-132.zip?download=1"))
DERIVATIVES=REC+"/files/derivatives.zip?download=1"
SOURCE_SHA={
"openswisshcc_v2_all_90_venous_HCC_lesion_size_and_primary_flags.csv":
 "a8291b4de55fdec75a59378218c017aedfa4bcb950ac4bde9813780c8b43fc42",
"openswisshcc_v2_primary_1_HCC_venous_lesion_per_subject.csv":
 "4e1882540f9d165a279bd5afab1b5983f5570e1e94bdebbb2fdb798c41f61432",
"openswisshcc_v2_primary_selection_summary.json":
 "31590e93813c0be862050a26865688b9ed8313185c366962875a7566d50e1a11"}
GRID=("native","3mm")
BINS=(12.5,25.0,50.0)
SHARDS=15
FEATURE_COLS=("original_glcm_Contrast","original_glcm_JointEntropy",
              "original_firstorder_Entropy","original_firstorder_InterquartileRange")
CSV_COLUMNS=("patient_id","selected_lesion","original_size_mm",
 "original_venous_image_member","original_image_sha256","original_venous_manual_mask_member",
 "original_mask_sha256","image_shape","mask_shape","source_voxel_spacing_x_mm",
 "source_voxel_spacing_y_mm","source_voxel_spacing_z_mm","mask_nonzero_voxel_count",
 "image_mask_affine_corner_mm","source_phase","grid","binWidth",
 "image_interpolation","mask_interpolation","pyradiomics_version",
 *FEATURE_COLS,"independent_subject_count_unit","external_cohort_replication_claim",
 "clinical_eligibility","MRI_RNA_associations_executed","claim_ceiling")
ERROR_COLUMNS=("patient_id","selected_lesion","source_archive","error_type","error_message",
 "source_mask_path","radiomics_extracted","clinical_eligibility","claim_ceiling")

def selected(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        if set(z.namelist())!=set(SOURCE_SHA):
            raise ValueError("SOURCE_MANIFEST_MEMBERS_NOT_ORIGINAL_FROZEN_THREE")
        data={k:z.read(k) for k in SOURCE_SHA}
    for k,v in SOURCE_SHA.items():
        if hashlib.sha256(data[k]).hexdigest()!=v:
            raise ValueError("FROZEN_59_PRIMARY_SELECTED_SOURCE_SHA_DRIFT:"+k)
    rows=list(csv.DictReader(io.StringIO(
        data["openswisshcc_v2_primary_1_HCC_venous_lesion_per_subject.csv"].decode("utf8"))))
    j=json.loads(data["openswisshcc_v2_primary_selection_summary.json"])
    if len(rows)!=59 or len({r["subject"] for r in rows})!=59:
        raise ValueError("EXPECTED_59_INDEPENDENT_EXTERNAL_PATIENTS")
    if (j["HCC_venous_source_lesions"]!=90
        or j["subjects_with_deterministic_largest_published_lesion"]!=59
        or j["subjects_HOLD_missing_any_candidate_lesion_size"]!=0
        or j["external_radiomics_replication"]!="NOT_EXECUTED"
        or j["claim_ceiling"]!="S0"):
        raise ValueError("SOURCE_PRIMARY_SELECTION_NOT_PREOUTCOME_OR_UNVERIFIED")
    if any(r["selection_status"]!="METADATA_PRESELECTED_ONLY_PENDING_IMAGE_MASK_ALIGNMENT"
       or r["radiomics_tests_executed"]!="NO"
       or r["clinical_eligible"]!="NOT_ASSESSED"
       or r["claim_ceiling"]!="S0"
       or not re.fullmatch(r"sub-\d{3}",r["subject"])
       or not re.fullmatch(r"L[1-5]",r["selected_lesion"])
       or not r["source_mask_path"].endswith(".nii.gz") for r in rows):
        raise ValueError("UNSAFE_SOURCE_SELECTION_OR_IMAGE_MASK_PROVENANCE")
    return sorted(rows,key=lambda r:r["subject"])

def group_url(pid):
    n=int(pid[4:])
    for max_id,url in IMG_GROUPS:
        if n<=max_id:return url
    raise ValueError("OUTSIDE_SOURCE_PATIENT_ARCHIVE_GROUP")

def image_member(names,pid):
    suffix=f"/{pid}/dyn/{pid}_acq-water_phase-venous_T1w.nii.gz"
    candidates=[n for n in names if ("/"+n).endswith(suffix)]
    if len(candidates)!=1:
        raise ValueError("NO_UNIQUE_EXACT_VENOUS_WATER_IMAGE:"+pid+":"+str(len(candidates)))
    return candidates[0]

def fetch_member(archive,url,name):
    info=archive.getinfo(name)
    if info.file_size<=352 or info.file_size>96*1024*1024 or info.compress_size>96*1024*1024:
        raise ValueError("NIFTI_IMAGE_OR_MASK_SIZE_BOUND_FAILED")
    data=get_member_with_ranges(url,info,archive.fp.total)
    if len(data)!=info.file_size:raise ValueError("SOURCE_NIFTI_MEMBER_BYTES_INCOMPLETE")
    return data

def analyze(pidrow,image_archive,mask_archive,image_url,ex):
    import numpy as np,nibabel as nib
    pid=pidrow["subject"]
    lesion=pidrow["selected_lesion"]
    im=image_member(image_archive.namelist(),pid)
    mask=pidrow["source_mask_path"]
    if mask not in mask_archive.NameToInfo:
        raise ValueError("FROZEN_VENOUS_MASK_PATH_MISSING_IN_ORIGINAL_ZIP")
    image_bytes=fetch_member(image_archive,image_url,im)
    mask_bytes=fetch_member(mask_archive,DERIVATIVES,mask)
    with tempfile.TemporaryDirectory(prefix="hcc_openswiss_multi_") as t:
        i=Path(t)/"image.nii.gz";m=Path(t)/"mask.nii.gz"
        i.write_bytes(image_bytes);m.write_bytes(mask_bytes)
        nii=nib.load(str(i));msk=nib.load(str(m))
        if nii.ndim!=3 or msk.ndim!=3 or nii.shape!=msk.shape:
            raise ValueError("NIFTI_IMAGE_MASK_SOURCE_SHAPE_MISMATCH")
        off=corner_offset_mm(nii.affine,msk.affine,msk.shape)
        if not math.isfinite(off) or off>0.5:
            raise ValueError("PATIENT_MASK_NOT_ALIGNED_WITH_EXACT_VENOUS_IMAGE")
        a=np.asarray(nii.dataobj,dtype=np.float32)
        b=np.asarray(msk.dataobj)
        selected_mask=b==1
        vox=int(selected_mask.sum())
        if vox<50 or vox>=a.size:
            raise ValueError("MASK_TOO_SMALL_OR_FULL_VOLUME_FOR_LOCKED_PILOT_ROI")
        if not np.isfinite(a[selected_mask]).all():
            raise ValueError("NONFINITE_MASKED_VENOUS_IMAGE_VOXELS")
        vals=[]
        for grid in GRID:
            for bw in BINS:
                features=ex[(grid,bw)].execute(str(i),str(m),label=1)
                num={k:float(features[k]) for k in FEATURE_COLS}
                if not all(math.isfinite(x) for x in num.values()):
                    raise ValueError("NONFINITE_VENOUS_RADIOMIC_FEATURE")
                vals.append({
                 "patient_id":pid,"selected_lesion":lesion,
                 "original_size_mm":pidrow["source_lesion_size_mm"],
                 "original_venous_image_member":im,
                 "original_image_sha256":hashlib.sha256(image_bytes).hexdigest(),
                 "original_venous_manual_mask_member":mask,
                 "original_mask_sha256":hashlib.sha256(mask_bytes).hexdigest(),
                 "image_shape":"x".join(map(str,nii.shape)),
                 "mask_shape":"x".join(map(str,msk.shape)),
                 "source_voxel_spacing_x_mm":round(float(nii.header.get_zooms()[0]),6),
                 "source_voxel_spacing_y_mm":round(float(nii.header.get_zooms()[1]),6),
                 "source_voxel_spacing_z_mm":round(float(nii.header.get_zooms()[2]),6),
                 "mask_nonzero_voxel_count":vox,
                 "image_mask_affine_corner_mm":round(off,6),
                 "source_phase":"original_native_venous_water",
                 "grid":grid,"binWidth":bw,
                 "image_interpolation":"NONE" if grid=="native" else "sitkBSpline",
                 "mask_interpolation":"NONE" if grid=="native" else "NEAREST_NEIGHBOR",
                 "pyradiomics_version":"3.1.0",**num,
                 "independent_subject_count_unit":"YES",
                 "external_cohort_replication_claim":"NO_INDIVIDUAL_SHARD",
                 "clinical_eligibility":"NOT_ASSESSED",
                 "MRI_RNA_associations_executed":"NO","claim_ceiling":"S0"})
    if len(vals)!=6:raise ValueError("INCOMPLETE_ORIGINAL_SIX_FACTORIAL_CELLS")
    return vals

def run_shard(manifest,shard):
    if not 0<=shard<SHARDS:raise ValueError("OUTSIDE_15_DECLARED_SHARDS")
    rows=manifest[4*shard:4*shard+4]
    if not 1<=len(rows)<=4:raise ValueError("EMPTY_PRESELECTED_PATIENT_SHARD")
    if version("pyradiomics")!="3.1.0":raise ValueError("PINNED_PYRAD_3_1_0_REQUIRED")
    ex={}
    for g in GRID:
        for bw in BINS:
            obj=make_extractor(g,bw)
            obj.settings["geometryTolerance"]=0.5
            ex[(g,bw)]=obj
    results=[];fail=[];current_url=None;image_archive=None
    with zipfile.ZipFile(HTTPRangeFile(DERIVATIVES)) as masks:
        try:
            for row in rows:
                pid=row["subject"];url=group_url(pid)
                if url!=current_url:
                    if image_archive:image_archive.close()
                    image_archive=zipfile.ZipFile(HTTPRangeFile(url))
                    current_url=url
                try:
                    recs=analyze(row,image_archive,masks,url,ex)
                    results+=recs
                    print("EXTERNAL_HCC_V2_VENOUS_SOURCE_REAL_PATIENT_PASS",pid,row["selected_lesion"],flush=True)
                except Exception as exc:
                    fail.append({"patient_id":pid,"selected_lesion":row["selected_lesion"],
                     "source_archive":url,
                     "error_type":type(exc).__name__,"error_message":str(exc)[:400],
                     "source_mask_path":row["source_mask_path"],
                     "radiomics_extracted":"NO","clinical_eligibility":"NOT_ASSESSED",
                     "claim_ceiling":"S0"})
                    print("EXTERNAL_HCC_V2_VENOUS_SOURCE_CASE_HOLD",pid,type(exc).__name__,
                          str(exc)[:150],flush=True)
        finally:
            if image_archive:image_archive.close()
    completed={r["patient_id"] for r in results}
    if len(results)!=6*len(completed) or len(completed)+len(fail)!=len(rows) or len(completed & {r["patient_id"] for r in fail}):
        raise ValueError("PARTIAL_CASE_RESULTS_OR_DOUBLE_COUNTING_IN_SOURCE_SHARD")
    return rows,results,fail

def fixture():
    assert SHARDS==15 and len(GRID)*len(BINS)==6 and len(FEATURE_COLS)==4
    assert group_url("sub-003").endswith("sub-001-sub-044.zip?download=1")
    assert group_url("sub-071").endswith("sub-044-sub-088.zip?download=1")
    assert image_member(["sub-001-sub-044/sub-003/dyn/sub-003_acq-water_phase-venous_T1w.nii.gz"],"sub-003").endswith("_T1w.nii.gz")
    try:image_member(["sub-001-sub-044/sub-003/dyn/sub-003_acq-water_phase-arterial_T1w.nii.gz"],"sub-003")
    except ValueError:pass
    else:raise AssertionError("ARTERIAL_WRONG_PILOT_VENOUS_SOURCE_SELECTED")
    print("HCC_OPENSWISS_V2_59_PATIENT_15_SHARD_VENOUS_MASK_SOURCE_CONTRACT_PASS")

def write_csv(path,columns,rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=columns)
        w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--primary-source-zip",type=Path)
    ap.add_argument("--shard",type=int)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/openswiss_v2_59case_extraction"))
    a=ap.parse_args()
    if a.offline_test:return fixture()
    if a.primary_source_zip is None or a.shard is None:
        raise ValueError("SHA256_VERIFIED_FROZEN_PRIMARY_MANIFEST_AND_SHARD_REQUIRED")
    manifest=selected(a.primary_source_zip)
    subset,results,fail=run_shard(manifest,a.shard)
    a.out_dir.mkdir(parents=True,exist_ok=True)
    write_csv(a.out_dir/f"external_hcc_venous_pyradiomics_shard_{a.shard}.csv",CSV_COLUMNS,results)
    write_csv(a.out_dir/f"external_hcc_venous_source_hold_shard_{a.shard}.csv",ERROR_COLUMNS,fail)
    meta={"status":"EXTERNAL_SOURCE_SHARD_COMPLETED_PARTIAL_RECORDED",
      "shard":a.shard,"expected_source_patients":[r["subject"] for r in subset],
      "n_expected":len(subset),"n_succeeded":len({x["patient_id"] for x in results}),
      "n_hold":len(fail),"n_feature_grid_rows":len(results),
      "original_source_artifact_id":13049177735,
      "mask_archive_source":DERIVATIVES,
      "original_Zenodo_patient_zip_entirely_downloaded":False,
      "clinical_n":"NOT_ASSESSED","RNA_12_tests":"NOT_EXECUTED",
      "external_cohort_replication":"NOT_ASSESSED_UNTIL_ALL_SHARDS_AGGREGATED",
      "claim_ceiling":"S0"}
    (a.out_dir/f"external_hcc_venous_source_shard_{a.shard}.json").write_text(
        json.dumps(meta,indent=2)+"\n")
    print("EXTERNAL_HCC_V2_REAL_VENOUS_PER_SHARD_STATUS",json.dumps(meta),flush=True)
if __name__=="__main__":main()
