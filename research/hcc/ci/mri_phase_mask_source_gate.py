#!/usr/bin/env python3
"""LiverHccSeg official source-space/ROI gate; independent from imaging-RNA outcomes.

Publication v1.1: masks are applicable to arterial ('art') and co-registered
portal venous ('art_pv') images. Raw 'pv' is not a source-authorized mask
coordinate reference merely because its NIfTI affine matches.
https://zenodo.org/records/8179129

Read-only 2-person pilot downloads bounded ZIP members, compares actual image
and ROI geometry and intensity support. No anatomical expert sign-off, clinical
eligibility, radiomics association or quiet baseline replacement.
"""
import argparse, csv, hashlib, json, math, re, tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

FROZEN = Path("research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv")
SOURCE = "https://zenodo.org/records/8179129"
SOURCE_VERSION = "v1.1"
SOURCE_PHASE_RULE = {"art": "DOCUMENTED_REFERENCE",
                     "art_pv": "DOCUMENTED_REGISTERED",
                     "pv": "RAW_NOT_DOCUMENTED_MASK_REFERENCE"}
PILOT_IDS = ("TCGA-BC-A10Y", "TCGA-DD-A4NH")
FIELDS = ("patient_id", "index_tumor", "image_phase", "source_member", "mask_member",
          "source_sha256", "mask_sha256", "geometry_status", "shape_source",
          "shape_mask", "max_affine_corner_offset_mm", "roi_voxels",
          "roi_finite_fraction", "roi_signal_median", "official_source_space",
          "anatomical_review", "temporal_eligibility", "same_lesion_rna",
          "candidate_final_status")

def frozen():
    with FROZEN.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=14 or len({x["patient_id"] for x in rows})!=14:
        raise ValueError("14 unique MRI candidates required")
    out={}
    for row in rows:
        pid=row["patient_id"]
        if not re.fullmatch(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}",pid):
            raise ValueError("Malformed TCGA case")
        n=int(row["representative_tumor_number"])
        if n<1 or n>20:
            raise ValueError("Invalid index tumor")
        if row["expert_review"]!="NOT_ASSESSED" or row["pretreatment_verified"]!="NOT_ASSESSED" or row["eligible_radiogenomics"]!="NOT_ASSESSED":
            raise ValueError("Unexpected clinical promotion in frozen selected tumor file")
        out[pid]=n
    if out["TCGA-BC-A10Y"]!=3:
        raise ValueError("Prior locked A10Y tumor3 selection was lost")
    return out

def source_rule(phase):
    if phase not in SOURCE_PHASE_RULE:
        raise ValueError("Unapproved phase")
    return SOURCE_PHASE_RULE[phase]

def scientific_decision(phase,geometry,review="NOT_ASSESSED",timing="NOT_ASSESSED",lesion="NOT_ASSESSED"):
    if review=="NOT_ASSESSED" or timing=="NOT_ASSESSED" or lesion=="NOT_ASSESSED":
        return "HOLD_SOURCE_SPACE_AND_CLINICAL"
    if source_rule(phase)=="RAW_NOT_DOCUMENTED_MASK_REFERENCE":
        return "HOLD_RAW_PV_NOT_SOURCE_AUTHORIZED"
    if geometry!="PASS_GEOMETRY_ONLY":
        return "HOLD_GEOMETRY"
    return "MANUAL_REVIEW_REQUIRED_NOT_AUTO_QUALIFIED"

def inventory_member(index,pid,name):
    hits=[m for m in index if m.startswith(pid+"/") or "/"+pid+"/" in m]
    hits=[m for m in hits if m.endswith("/"+name) and "/__MACOSX/" not in "/"+m and "/._" not in m]
    if len(hits)!=1:
        raise ValueError(f"{pid} expected 1 {name}, got {len(hits)}")
    return hits[0]

def sha(b):
    return hashlib.sha256(b).hexdigest()

def analyze_image(image,mask,phase):
    import numpy as np
    from mri_pv_pixel_overlay_audit import corner_offset_mm
    base=dict(geometry_status="NOT_ASSESSED",shape_source=str(image.shape),
              shape_mask=str(mask.shape),max_affine_corner_offset_mm=None,
              roi_voxels=0,roi_finite_fraction=None,roi_signal_median=None)
    if len(image.shape)!=3 or image.shape!=mask.shape:
        base["geometry_status"]="SHAPE_MISMATCH"
        return base
    offset=corner_offset_mm(image.affine,mask.affine,image.shape)
    base["max_affine_corner_offset_mm"]=round(offset,6)
    if not math.isfinite(offset) or offset>0.5:
        base["geometry_status"]="AFFINE_MISMATCH"
        return base
    m=np.asanyarray(mask.dataobj)>0
    n=int(m.sum())
    base["roi_voxels"]=n
    if n<=50 or n>=int(m.size):
        base["geometry_status"]="INVALID_ROI"
        return base
    values=np.asarray(image.dataobj,dtype=np.float32)[m]
    fraction=float(np.isfinite(values).mean())
    base["roi_finite_fraction"]=round(fraction,6)
    if fraction!=1:
        base["geometry_status"]="NONFINITE_ROI"
        return base
    base["roi_signal_median"]=round(float(np.median(values)),6)
    base["geometry_status"]="PASS_GEOMETRY_ONLY"
    return base

def audit_one(archive,pid,idx):
    import nibabel as nib
    import numpy as np
    from io import BytesIO
    from fast_zip_member_range import get_member_with_ranges
    from zenodo_nifti_zip_inventory import ARCHIVE
    index=archive.NameToInfo
    mpath=inventory_member(index,pid,f"rater1_tumor{idx}.nii.gz")
    member_paths={"mask":mpath}
    for phase in SOURCE_PHASE_RULE:
        member_paths[phase]=inventory_member(index,pid,("art_pv" if phase=="art_pv" else phase)+".nii.gz")
    extracted={}
    for key,mpath in member_paths.items():
        info=archive.getinfo(mpath)
        if info.file_size>96*1024*1024 or info.compress_size>96*1024*1024:
            raise ValueError("Source member exceeds 96MiB bound")
        binary=get_member_with_ranges(ARCHIVE,info,archive.fp.total)
        extracted[key]=binary
    # Load each source .nii.gz into a local transient directory; no bytes uploaded.
    with tempfile.TemporaryDirectory(prefix="hcc_source_space_") as temp:
        loaded={}
        for label,blob in extracted.items():
            p=Path(temp)/(label+".nii.gz")
            p.write_bytes(blob)
            loaded[label]=nib.load(str(p))
        mask=loaded["mask"]
        rows=[]
        for phase in SOURCE_PHASE_RULE:
            data=analyze_image(loaded[phase],mask,phase)
            rows.append({
                "patient_id":pid,"index_tumor":idx,"image_phase":phase,
                "source_member":member_paths[phase],"mask_member":member_paths["mask"],
                "source_sha256":sha(extracted[phase]),"mask_sha256":sha(extracted["mask"]),
                **data,"official_source_space":source_rule(phase),
                "anatomical_review":"NOT_ASSESSED",
                "temporal_eligibility":"NOT_ASSESSED",
                "same_lesion_rna":"NOT_ASSESSED",
                "candidate_final_status":scientific_decision(phase,data["geometry_status"]),
            })
    return rows

def aggregate(rows,pilot_ids):
    if len(rows)!=3*len(pilot_ids) or {(r["patient_id"],r["image_phase"]) for r in rows}!={(p,phase) for p in pilot_ids for phase in SOURCE_PHASE_RULE}:
        raise ValueError("Incomplete patient/phase evidence")
    if any(r["candidate_final_status"]!="HOLD_SOURCE_SPACE_AND_CLINICAL" for r in rows):
        raise ValueError("No image geometry may auto-certify treatment/tumor")
    result={"status":"REVIEW_SOURCE_REGISTRATION_AND_EXPERT_ADJUDICATION_REQUIRED",
            "official_source":SOURCE,"official_version":SOURCE_VERSION,
            "frozen_total_candidates":14,"pilot_subjects":len(pilot_ids),
            "pilot_case_ids":list(pilot_ids),
            "phase_geometry_counts":{phase:{status:sum(r["image_phase"]==phase and r["geometry_status"]==status for r in rows)
                for status in sorted(set(r["geometry_status"] for r in rows if r["image_phase"]==phase))}
                for phase in SOURCE_PHASE_RULE},
            "study_source_contract":"MASK_VALID_ON_ART_AND_CO_REGISTERED_ART_PV; RAW_PV_NOT_LISTED",
            "source_reference_validated_by_code":False,
            "qualified_roi_expert_reviews":0,"patient_specific_pretreatment_verified":0,
            "same_lesion_RNA_confirmed":0,"eligible_mri_rna_n":"NOT_ASSESSED",
            "previous_raw_PV_ICC_approved_for_biology":False,
            "primary_twelve_mri_rna_tests":"NOT_EXECUTED",
            "HCC12":"PARTIAL","HCC14":"PARTIAL","HCC17":"PENDING",
            "HCC20":"PENDING","manuscript_claim_ceiling":"S0",
            "no_RNA_association_or_image_pixel_export":True,
            "generated_utc":datetime.now(timezone.utc).isoformat()}
    return result

def clinical_queue():
    # P0/1/2 reflect GDC source evidence priority, NOT eligibility/exclusions.
    priorities={
      "TCGA-BC-A10Y":"P0","TCGA-DD-A4NH":"P0",
      "TCGA-G3-A25T":"P0","TCGA-G3-AAV1":"P0",
      "TCGA-BC-A5W4":"P1","TCGA-BC-A3KG":"P1",
      "TCGA-DD-A4NF":"P1","TCGA-DD-A4NJ":"P1","TCGA-G3-A3CJ":"P1"}
    cases=frozen()
    return [{"patient_id":p,"priority":priorities.get(p,"P2"),
             "selected_tumor":n,"original_PV_features":"HOLD_SOURCE_SPACE_REVIEW",
             "official_ART_source_roi_review":"UNRESOLVED",
             "registered_ART_PV_source_roi_review":"UNRESOLVED",
             "raw_PV_mask_anatomy_reviewer":"UNRESOLVED",
             "MRI_before_HCC_therapy":"UNRESOLVED",
             "MRI_index_lesion_same_as_sequenced_RNA":"UNRESOLVED",
             "authoritative_source_url":"","reviewer_qualification":"",
             "review_date":"","decision":"HOLD_UNRESOLVED_NOT_EXCLUDED"}
            for p,n in sorted(cases.items())]

def offline():
    import numpy as np
    cases=frozen()
    assert len(cases)==14
    assert len(clinical_queue())==14
    assert [q["priority"] for q in clinical_queue()].count("P0")==4
    assert [q["priority"] for q in clinical_queue()].count("P1")==5
    assert all(q["decision"]=="HOLD_UNRESOLVED_NOT_EXCLUDED" for q in clinical_queue())
    assert source_rule("art")=="DOCUMENTED_REFERENCE"
    assert source_rule("art_pv")=="DOCUMENTED_REGISTERED"
    assert source_rule("pv")=="RAW_NOT_DOCUMENTED_MASK_REFERENCE"
    assert scientific_decision("pv","PASS_GEOMETRY_ONLY")=="HOLD_SOURCE_SPACE_AND_CLINICAL"
    assert scientific_decision("art_pv","AFFINE_MISMATCH")=="HOLD_SOURCE_SPACE_AND_CLINICAL"
    import nibabel as nib
    arr=np.ones((8,8,8),dtype=np.float32)
    mask=np.zeros_like(arr); mask[1:5,1:5,1:5]=1
    image=nib.Nifti1Image(arr,np.eye(4))
    roi=nib.Nifti1Image(mask,np.eye(4))
    assert analyze_image(image,roi,"pv")["geometry_status"]=="PASS_GEOMETRY_ONLY"
    shifted=nib.Nifti1Image(arr,np.diag([1,1,2,1]))
    assert analyze_image(shifted,roi,"art_pv")["geometry_status"]=="AFFINE_MISMATCH"
    assert analyze_image(nib.Nifti1Image(arr[:,:,:7],np.eye(4)),roi,"art_pv")["geometry_status"]=="SHAPE_MISMATCH"
    print("HCC_MRI_SOURCE_SPACE_OFFICIAL_CONTRACT_AND_CLINICAL_HOLD_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("offline","live","queue"),required=True)
    p.add_argument("--max-cases",type=int,default=2,choices=(1,2))
    p.add_argument("--out-dir",default="artifacts/hcc_mri_source_space")
    a=p.parse_args()
    if a.mode=="offline":
        offline();return
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    q=clinical_queue()
    with (out/"hcc_mri14_source_and_clinical_review_queue.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(q[0]));w.writeheader();w.writerows(q)
    if a.mode=="queue":
        print("HCC_MRI_SOURCE_SPACE_14_CASE_REVIEW_QUEUE_CREATED; ELIGIBLE_NOT_ASSESSED")
        return
    from mri_mask_voxel_audit import HTTPRangeFile
    from zenodo_nifti_zip_inventory import ARCHIVE
    cases=frozen()
    chosen=PILOT_IDS[:a.max_cases]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        rows=[row for pid in chosen for row in audit_one(archive,pid,cases[pid])]
    with (out/"hcc_mri_source_space_pilot.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    report=aggregate(rows,chosen)
    (out/"hcc_mri_source_space_pilot_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    # Deliberate scientific HOLD: actual data can never auto-qualify patients.

if __name__=="__main__":
    main()
