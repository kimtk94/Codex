#!/usr/bin/env python3
"""14-person HCC official registered portal venous MRI feature sensitivity.

Seven deterministic two-person shards, 2 expert readers, two portal-venous
image sources: archived native pv.nii.gz and axis-reoriented official art_pv.nii.gz.
Ten frozen PyRadiomics features per phase/reader. This is purely source-space
measurement reproducibility. No MRI–RNA association, no clinical eligibility.
"""
import argparse,csv,hashlib,json,math,tempfile
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from fast_zip_member_range import get_member_with_ranges
from mri_mask_voxel_audit import HTTPRangeFile
from mri_phase_mask_source_gate import frozen,inventory_member
from mri_p0_raw_vs_registered_pv_radiomics_pilot import orient_to_mask,pixels
from mri_pv_pyradiomics_rater_icc import make_extractor,FEATURES_to_names,feature_icc,PARAMS
from zenodo_nifti_zip_inventory import ARCHIVE

PHASES=("raw_pv","reoriented_art_pv")
RATERS=("rater1","rater2")
ALL_FEATURES=tuple(FEATURES_to_names())
LOCKED=("original_firstorder_Entropy","original_firstorder_InterquartileRange",
        "original_glcm_Contrast")
SHARDS=7
SRC="https://zenodo.org/records/8179129"
FIELDS=("patient_id","selected_tumor","rater","phase",
        "source_member","source_sha256","mask_member","mask_sha256",
        "physical_affine_offset_mm","voxel_axes","voxel_axis_signs",
        "roi_voxels","roi_finite_fraction","roi_nonzero_fraction","roi_median","roi_iqr",
        *ALL_FEATURES,"source_registration_expert_review",
        "MRI_pretreatment_verified","RNA_same_index_lesion",
        "eligible_for_MRI_RNA","research_claim_ceiling")

def case_sources(archive,pid,tumor,td):
    import nibabel as nib
    names=("pv","art_pv",f"rater1_tumor{tumor}",f"rater2_tumor{tumor}")
    loaded={};meta={}
    for name in names:
        member=inventory_member(archive.NameToInfo,pid,name+".nii.gz")
        info=archive.getinfo(member)
        if info.file_size>96*1024*1024 or info.compress_size>96*1024*1024:
            raise ValueError("OFFICIAL_ARCHIVE_MEMBER_GT_96M")
        binary=get_member_with_ranges(ARCHIVE,info,archive.fp.total)
        digest=hashlib.sha256(binary).hexdigest()
        path=Path(td)/(name+".nii.gz")
        path.write_bytes(binary)
        loaded[name]=nib.load(str(path))
        meta[name]={"member":member,"sha256":digest}
    return loaded,meta

def run_case(archive,pid,tumor,extractor):
    import nibabel as nib
    from mri_pv_pixel_overlay_audit import corner_offset_mm
    with tempfile.TemporaryDirectory(prefix="hcc_mri14_registered_phase_") as t:
        images,source=case_sources(archive,pid,tumor,t)
        mask=images[f"rater1_tumor{tumor}"]
        reg,order,sign=orient_to_mask(images["art_pv"],mask)
        if order!=[0,1,2] or sum(s<0 for s in sign) not in (1,2):
            raise ValueError("FROZEN_14_PATIENT_SOURCE_ORIENTATION_UNEXPECTED")
        if corner_offset_mm(images["pv"].affine,mask.affine,mask.shape)>0.5:
            raise ValueError("RAW_PV_HEADER_DRIFT")
        import radiomics
        from importlib.metadata import version
        if version("pyradiomics")!="3.1.0":
            raise ValueError("PYRADIOMICS_DISTRIBUTION_DRIFT")
        rows=[]
        for rater in RATERS:
            name=f"{rater}_tumor{tumor}"
            roi=images[name]
            if roi.shape!=mask.shape:
                raise ValueError("RATER_MASK_SHAPE_CHANGED")
            for phase,image,key in (("raw_pv",images["pv"],"pv"),("reoriented_art_pv",reg,"art_pv")):
                offset=corner_offset_mm(image.affine,roi.affine,roi.shape)
                if offset>0.5:raise ValueError("PHYSICAL_ROI_ALIGNMENT_FAILED")
                src_file=Path(t)/(phase+"_"+rater+".nii.gz")
                mask_file=Path(t)/(phase+"_"+rater+"_roi.nii.gz")
                nib.save(image,str(src_file))
                nib.save(roi,str(mask_file))
                extracted=extractor.execute(str(src_file),str(mask_file),label=1)
                measurements={key:float(extracted[key]) for key in ALL_FEATURES}
                if not all(math.isfinite(v) for v in measurements.values()):
                    raise ValueError("NONFINITE_SOURCE_PHASE_RADIOMIC_FEATURE")
                stats=pixels(image,roi)
                rows.append({
                    "patient_id":pid,"selected_tumor":tumor,"rater":rater,"phase":phase,
                    "source_member":source[key]["member"],"source_sha256":source[key]["sha256"],
                    "mask_member":source[name]["member"],"mask_sha256":source[name]["sha256"],
                    "physical_affine_offset_mm":round(offset,6),
                    "voxel_axes":";".join(map(str,order)),
                    "voxel_axis_signs":";".join(map(str,sign)) if phase=="reoriented_art_pv" else "NONE",
                    **stats,**measurements,
                    "source_registration_expert_review":"NOT_ASSESSED",
                    "MRI_pretreatment_verified":"NOT_ASSESSED",
                    "RNA_same_index_lesion":"NOT_ASSESSED",
                    "eligible_for_MRI_RNA":"NOT_ASSESSED",
                    "research_claim_ceiling":"S0"})
        if len(rows)!=4:raise ValueError("MISSING_RATER_OR_PHASE")
        print("HCC_MRI14_REGISTERED_SOURCE_CASE_PASS",pid,
              "mask",tumor,"axis_flip",sum(s<0 for s in sign),flush=True)
        return rows

def verify_shard(rows,batch_index):
    cases=frozen()
    ids=sorted(cases)[batch_index*2:batch_index*2+2]
    expected={(p,r,phase) for p in ids for r in RATERS for phase in PHASES}
    observed={(row["patient_id"],row["rater"],row["phase"]) for row in rows}
    if len(rows)!=8 or observed!=expected:
        raise ValueError("CASE_PHASE_RATER_2x2x2_SHARD_INCOMPLETE")
    if any(row["selected_tumor"]!=cases[row["patient_id"]] for row in rows):
        raise ValueError("FROZEN_INDEX_LESION_MISMATCH")
    if any(row["eligible_for_MRI_RNA"]!="NOT_ASSESSED"
           or row["RNA_same_index_lesion"]!="NOT_ASSESSED"
           or row["MRI_pretreatment_verified"]!="NOT_ASSESSED"
           or row["research_claim_ceiling"]!="S0" for row in rows):
        raise ValueError("FORBIDDEN_CLINICAL_PROMOTION")
    if any(float(row["physical_affine_offset_mm"])>0.5 for row in rows):
        raise ValueError("UNAPPROVED_SOURCE_GEOMETRY")
    if any(not math.isfinite(float(row[x])) for row in rows for x in ALL_FEATURES):
        raise ValueError("NONFINITE_RADIOMIC_FEATURE")
    return ids

def offline():
    assert len(frozen())==14 and frozen()["TCGA-BC-A10Y"]==3
    assert SHARDS==7 and len(ALL_FEATURES)==10 and len(LOCKED)==3
    assert set(LOCKED).issubset(ALL_FEATURES)
    allids=[pid for i in range(SHARDS) for pid in sorted(frozen())[i*2:i*2+2]]
    assert len(allids)==len(set(allids))==14
    good=[]
    for pid in allids[:2]:
        for r in RATERS:
            for phase in PHASES:
                good.append({"patient_id":pid,"selected_tumor":frozen()[pid],
                             "rater":r,"phase":phase,
                             "eligible_for_MRI_RNA":"NOT_ASSESSED",
                             "RNA_same_index_lesion":"NOT_ASSESSED",
                             "MRI_pretreatment_verified":"NOT_ASSESSED",
                             "research_claim_ceiling":"S0",
                             "physical_affine_offset_mm":0.0,
                             **{x:float(i+1) for i,x in enumerate(ALL_FEATURES)}})
    assert verify_shard(good,0)==sorted(frozen())[:2]
    bad=[dict(r) for r in good];bad[0]["eligible_for_MRI_RNA"]="YES"
    try:verify_shard(bad,0)
    except ValueError:pass
    else:raise AssertionError("CLINICAL_PROMOTION_WAS_NOT_REJECTED")
    print("HCC_14_REGISTERED_PV_7_SHARD_10_FEATURES_CLINICAL_HOLD_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--shard-index",type=int,default=None)
    p.add_argument("--out-dir",default="artifacts/hcc14_registered_phase")
    args=p.parse_args()
    if args.offline_test:offline();return
    if args.shard_index is None or not 0<=args.shard_index<SHARDS:
        raise ValueError("EXACT_7_FROZEN_SHARDS_REQUIRED")
    cases=frozen()
    ids=sorted(cases)[args.shard_index*2:args.shard_index*2+2]
    extractor=make_extractor()
    extractor.settings["geometryTolerance"]=0.5
    result=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        for pid in ids:
            result+=run_case(archive,pid,cases[pid],extractor)
    verify_shard(result,args.shard_index)
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/f"hcc_mri14_registered_phase_shard_{args.shard_index}.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(result)
    summary={"status":"PASS_SOURCE_FEATURE_EXTRACTION_DESCRIPTIVE_ONLY",
      "official_dataset":SRC,"source_case_ids":ids,
      "shard_index":args.shard_index,"shard_rows":len(result),
      "phase_arms":list(PHASES),"reader_masks":list(RATERS),
      "features_count":len(ALL_FEATURES),"frozen_locked_primary_features":list(LOCKED),
      "pyradiomics_distribution":"3.1.0","pyradiomics_settings":dict(PARAMS,geometryTolerance=0.5),
      "no_registered_image_resampling":True,"source_zip_crc_and_sha":True,
      "qualified_clinical_n":"NOT_ASSESSED",
      "12_primary_MRI_RNA_associations":"NOT_EXECUTED",
      "claim_ceiling":"S0"}
    (out/f"hcc_mri14_registered_phase_shard_{args.shard_index}.json").write_text(
        json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print("HCC_MRI14_FROZEN_REGISTERED_PHASE_SHARD_DONE",args.shard_index,
          len(ids),"cases",len(result),"rows",flush=True)

if __name__=="__main__":main()
