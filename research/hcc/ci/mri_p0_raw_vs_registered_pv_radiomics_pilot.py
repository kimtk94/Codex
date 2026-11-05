#!/usr/bin/env python3
"""Two-case source-space PV pilot: real voxels, both reader masks, three locked features.
Official LiverHccSeg v1.1 art_pv is portal venous co-registered to arterial space.
Never infer qualified MRI-RNA patients or automatically replace historical raw-PV features.
ZIP CRC, fixed selected tumor and source SHA required. No source pixels exported.
"""
import argparse,csv,hashlib,json,math,tempfile
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from mri_phase_mask_source_gate import frozen,PILOT_IDS,inventory_member
from mri_pv_pixel_overlay_audit import corner_offset_mm
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from zenodo_nifti_zip_inventory import ARCHIVE

BASE=Path("research/hcc/HCC_MRI_P0_2CASE_ACTUAL_SOURCE_SPACE_20261031.json")
FEATURES=("original_firstorder_Entropy","original_firstorder_InterquartileRange","original_glcm_Contrast")

def orient_to_mask(img,mask):
    import nibabel as nib
    from nibabel.orientations import io_orientation,ornt_transform,inv_ornt_aff,apply_orientation
    t=ornt_transform(io_orientation(img.affine),io_orientation(mask.affine))
    arr=apply_orientation(np.asarray(img.dataobj,dtype=np.float32),t)
    aff=img.affine @ inv_ornt_aff(t,img.shape)
    if arr.shape!=mask.shape or corner_offset_mm(aff,mask.affine,mask.shape)>0.5:
        raise ValueError("REORIENTATION_GEOMETRY_NOT_WITHIN_0_5MM")
    return nib.Nifti1Image(arr,aff),[int(v) for v in t[:,0]],[int(v) for v in t[:,1]]

def pixels(img,mask):
    vals=np.asarray(img.dataobj,dtype=np.float32)[np.asarray(mask.dataobj)>0]
    if len(vals)<=50 or not np.isfinite(vals).all():
        raise ValueError("ROI_NONFINITE_OR_EMPTY")
    return dict(roi_voxels=len(vals),roi_finite_fraction=1,
        roi_nonzero_fraction=round(float(np.mean(vals!=0)),6),
        roi_median=round(float(np.median(vals)),6),
        roi_iqr=round(float(np.percentile(vals,75)-np.percentile(vals,25)),6))

def nmi(a,b,liver):
    ok=(liver>0)&np.isfinite(a)&np.isfinite(b)&(a!=0)&(b!=0)
    ids=np.flatnonzero(ok)
    if len(ids)<500:raise ValueError("COMMON_LIVER_VOXEL_COUNT_LOW")
    rng=np.random.default_rng(20261031)
    ids=rng.choice(ids,size=min(40000,len(ids)),replace=False)
    def q(v):
        x=np.asarray(v.flat[ids],dtype=np.float64);lo,hi=np.percentile(x,[1,99])
        if hi<=lo:raise ValueError("DEGENERATE_PHASE_SIGNAL")
        return np.minimum(31,np.floor((np.clip(x,lo,hi)-lo)/(hi-lo)*32).astype("int64"))
    x,y=q(a),q(b)
    h=np.bincount(x*32+y,minlength=1024).reshape(32,32).astype(np.float64)
    h/=h.sum()
    def e(z):
        z=z[z>0]
        return float(-np.sum(z*np.log2(z)))
    return round((e(h.sum(0))+e(h.sum(1)))/e(h),6),len(ids)

def features(img,mask,tmp,label,enabled):
    if not enabled:return {k:None for k in FEATURES}
    import nibabel as nib
    from mri_pv_pyradiomics_rater_icc import make_extractor
    extractor=make_extractor()
    # Same setting in both source arms; record the tolerance explicitly.
    extractor.settings["geometryTolerance"]=0.5
    i=Path(tmp)/(label+"_im.nii.gz");m=Path(tmp)/(label+"_msk.nii.gz")
    nib.save(img,str(i));nib.save(mask,str(m))
    result=extractor.execute(str(i),str(m),label=1)
    values={k:round(float(result[k]),8) for k in FEATURES}
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError("NONFINITE_LOCKED_MRI_FEATURE")
    return values

def fetch(archive,pid,index,baseline,tmp):
    import nibabel as nib
    names=("art","pv","art_pv","rater1_liver",
           f"rater1_tumor{index}",f"rater2_tumor{index}")
    out={};hashes={};members={}
    old={r["phase"]:r["sha256"] for r in baseline["measurements"]}
    old[f"rater1_tumor{index}"]=baseline["mask_sha256"]
    for name in names:
        member=inventory_member(archive.NameToInfo,pid,name+".nii.gz")
        info=archive.getinfo(member)
        if info.file_size>96*1024*1024 or info.compress_size>96*1024*1024:
            raise ValueError("NIFTI_ARCHIVE_MEMBER_TOO_LARGE")
        blob=get_member_with_ranges(ARCHIVE,info,archive.fp.total)
        digest=hashlib.sha256(blob).hexdigest()
        if name in old and old[name]!=digest:raise ValueError("PINNED_SOURCE_SHA_DRIFT")
        p=Path(tmp)/(name+".nii.gz");p.write_bytes(blob)
        out[name]=nib.load(str(p));hashes[name]=digest;members[name]=member
    return out,hashes,members

def case(archive,pid,baseline,enabled):
    index=frozen()[pid]
    if index!=baseline["index_tumor"]:raise ValueError("INDEX_TUMOR_CHANGED")
    with tempfile.TemporaryDirectory(prefix="hcc_mri_p0_corrected_phase_") as tmp:
        images,hashes,members=fetch(archive,pid,index,baseline,tmp)
        mask1=images[f"rater1_tumor{index}"]
        reg,perm,sign=orient_to_mask(images["art_pv"],mask1)
        if corner_offset_mm(images["art"].affine,mask1.affine,mask1.shape)>0.5:
            raise ValueError("ART_MASK_ALIGNMENT_CHANGED")
        if corner_offset_mm(images["pv"].affine,mask1.affine,mask1.shape)>0.5:
            raise ValueError("RAW_PV_MASK_ALIGNMENT_CHANGED")
        if not any(x<0 for x in sign):raise ValueError("SOURCE_ORIENTATION_WAS_NOT_REVERSED")
        liver=np.asarray(images["rater1_liver"].dataobj)
        if liver.shape!=mask1.shape:raise ValueError("LIVER_SHAPE_DIFFERENT")
        art_data=np.asarray(images["art"].dataobj,dtype=np.float32)
        native_data=np.asarray(images["pv"].dataobj,dtype=np.float32)
        corr_data=np.asarray(reg.dataobj,dtype=np.float32)
        original_nmi,n_original=nmi(art_data,native_data,liver)
        corrected_nmi,n_corrected=nmi(art_data,corr_data,liver)
        diagnostic=dict(patient_id=pid,index_tumor=index,source_axis_permutation=perm,
            source_axis_sign=sign,corner_offset_after_reorientation_mm=round(
                corner_offset_mm(reg.affine,mask1.affine,mask1.shape),6),
            nmi_native_pv_vs_art=original_nmi,nmi_registered_pv_vs_art=corrected_nmi,
            nmi_registered_minus_raw=round(corrected_nmi-original_nmi,6),
            nmi_common_native_liver_voxels=n_original,
            nmi_common_registered_liver_voxels=n_corrected,
            nmi_descriptive_only=True,independent_anatomical_expert_review="NOT_ASSESSED",
            MRI_before_therapy="NOT_ASSESSED",RNA_same_lesion="NOT_ASSESSED")
        rows=[]
        for reader in ("rater1","rater2"):
            k=f"{reader}_tumor{index}";m=images[k]
            if m.shape!=mask1.shape or corner_offset_mm(m.affine,mask1.affine,m.shape)>0.5:
                raise ValueError("SECOND_READER_MASK_GEOMETRY_MISMATCH")
            for phase,im in (("raw_pv",images["pv"]),("reoriented_art_pv",reg)):
                off=corner_offset_mm(im.affine,m.affine,m.shape)
                if off>0.5:raise ValueError("ROI_VOXELS_SOURCE_ALIGNMENT_FAILED")
                source_key="pv" if phase=="raw_pv" else "art_pv"
                rows.append(dict(patient_id=pid,selected_tumor=index,reader=reader,
                    phase=phase,source_member=members[source_key],
                    mask_member=members[k],source_sha256=hashes[source_key],
                    mask_sha256=hashes[k],corner_offset_mm=round(off,6),
                    reorientation="NONE" if phase=="raw_pv" else "/".join(map(str,sign)),
                    interpolation_applied=False,**pixels(im,m),
                    **features(im,m,tmp,phase+"_"+reader,enabled),
                    expert_anatomic_acceptance="NOT_ASSESSED",
                    pretreatment="NOT_ASSESSED",RNA_same_lesion="NOT_ASSESSED",
                    MRI_RNA_eligible="NOT_ASSESSED"))
        return diagnostic,rows

def test():
    import nibabel as nib
    shape=(9,11,7)
    x=np.arange(np.prod(shape),dtype=np.float32).reshape(shape)
    mask=nib.Nifti1Image(np.ones(shape,dtype=np.uint8),np.eye(4))
    source=np.diag([-1.,-1.,1.,1.]);source[0,3]=shape[0]-1;source[1,3]=shape[1]-1
    out,perm,sign=orient_to_mask(nib.Nifti1Image(x,source),mask)
    assert perm==[0,1,2] and sign==[-1,-1,1]
    assert np.array_equal(np.asarray(out.dataobj),x[::-1,::-1,:])
    displaced=np.eye(4);displaced[0,3]=5
    try:orient_to_mask(nib.Nifti1Image(x,displaced),mask)
    except ValueError:pass
    else:raise AssertionError("TRUE_TRANSLATION_MUST_NOT_BE_REMOVED")
    signal=np.arange(1000,dtype=np.float32).reshape(10,10,10)+1
    mi,n=nmi(signal,signal,np.ones_like(signal))
    assert n==1000 and mi>1.99
    assert frozen()["TCGA-BC-A10Y"]==3
    print("HCC_SOURCE_REGISTERED_PV_ACTUAL_VOXEL_ORIENTATION_SYNTHETIC_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--radiomics",action="store_true")
    ap.add_argument("--out-dir",default="artifacts/hcc_p0_registered_vp")
    args=ap.parse_args()
    if args.offline_test:test();return
    b=json.loads(BASE.read_text())
    if b["snapshot"]!="HCC_MRI_P0_SOURCE_SPACE_TWO_CASE_ACTUAL_v1":
        raise ValueError("UNEXPECTED_PILOT_BASELINE")
    old={x["patient_id"]:x for x in b["pilots"]}
    if set(old)!=set(PILOT_IDS):raise ValueError("PATIENT_COHORT_ID_CHANGED")
    diagnostic=[];rows=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        for pid in PILOT_IDS:
            d,r=case(archive,pid,old[pid],args.radiomics)
            diagnostic.append(d);rows+=r
    if len(rows)!=8 or len(diagnostic)!=2:
        raise ValueError("EXPECTED_2_PATIENT_2_RATER_2_PHASE_CELLS")
    if any(r["MRI_RNA_eligible"]!="NOT_ASSESSED" for r in rows):
        raise ValueError("FORBIDDEN_BIOLOGICAL_ELIGIBILITY_PROMOTION")
    folder=Path(args.out_dir);folder.mkdir(parents=True,exist_ok=True)
    with (folder/"hcc_mri_p0_raw_vs_registered_pv_features.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    summary=dict(status="TWO_CASE_REAL_SOURCE_PIXEL_PILOT_DESCRIPTIVE_HOLD",
       dataset="https://zenodo.org/records/8179129",patients=diagnostic,
       feature_panel=list(FEATURES),three_locked_features_extracted=args.radiomics,
       number_of_phase_rater_rows=len(rows),source_nifti_exported=False,
       qualified_clinical_n="NOT_ASSESSED",MRI_RNA_12_tests="NOT_EXECUTED",
       HCC12="PARTIAL",HCC13="PARTIAL",HCC20="PENDING",claim_ceiling="S0")
    (folder/"hcc_mri_p0_raw_vs_registered_pv_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary))

if __name__=="__main__":main()
