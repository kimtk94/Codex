#!/usr/bin/env python3
"""Independent pure-Python IBSI1 3D GLCM Contrast ACUI phantom benchmark.

No PyRadiomics, numpy, synthetic phantom, or featureextractor. Reads IBSI-1
official 5x4x4 NIfTI signed int16 image and 74-voxel ROI; enumerates
13 3D directional Chebyshev-one (undirected) offsets. Contrast is invariant
under symmetric counts, so count each directed edge once per direction.
3D:avg is unweighted average of direction-specific contrasts;
3D:mrg is contrast after pooling all direction pairs.

Official rounded references: 5.32 / 5.12. This independent mathematical
PASS establishes valid reference inputs, not full PyRadiomics IBSI compliance.
"""
import argparse,csv,gzip,hashlib,itertools,json,math,struct
from datetime import datetime,timezone
from pathlib import Path
from mri_ibsi1_official_phantom_benchmark import PHANTOM_SUB,find_original_files,source_info

DIM=(5,4,4)
ROI=74
REF_AVG=5.32
REF_MRG=5.12
DIFFERENCE=0.01  # enough for rounding to two decimals

def voxels(path):
    with gzip.open(path,"rb") as f:data=f.read()
    if len(data)>4096 or len(data)<512:
        raise ValueError("IBSI small NIfTI unexpected size")
    if struct.unpack_from("<i",data,0)[0]!=348:
        raise ValueError("Not original little-endian NIfTI1")
    dimensions=struct.unpack_from("<8h",data,40)
    datatype,bitpix=struct.unpack_from("<hh",data,70)
    offset=int(struct.unpack_from("<f",data,108)[0])
    if dimensions[:4]!=(3,*DIM) or datatype!=4 or bitpix!=16 or offset<352:
        raise ValueError("Original IBSI1 5x4x4 signed int16 format changed")
    if len(data)<offset+160:raise ValueError("Short IBSI NIfTI data")
    volume=struct.unpack_from("<80h",data,offset)
    return volume

def value(arr,x,y,z):
    return arr[x+DIM[0]*(y+DIM[1]*z)]

def compute(img,mask):
    if len(img)!=80 or len(mask)!=80:
        raise ValueError("Bad phantom size")
    if set(mask)!={0,1} or sum(mask)!=ROI:
        raise ValueError("Official binary ROI is 74/80")
    if set(v for i,v in enumerate(img) if mask[i])!={1,3,4,6}:
        raise ValueError("Original IBSI1 gray levels unexpectedly altered")
    offsets=[d for d in itertools.product((-1,0,1),repeat=3) if d>(0,0,0)]
    if len(offsets)!=13:
        raise ValueError("13 directions not detected")
    directional=[];merged_sq=0;merged_count=0
    for dx,dy,dz in offsets:
        sq=cnt=0
        for x,y,z in itertools.product(range(5),range(4),range(4)):
            tx,ty,tz=x+dx,y+dy,z+dz
            if 0<=tx<5 and 0<=ty<4 and 0<=tz<4 and value(mask,x,y,z) and value(mask,tx,ty,tz):
                sq+=(value(img,x,y,z)-value(img,tx,ty,tz))**2
                cnt+=1
        if cnt==0:raise ValueError("No GLCM neighbor pairs in direction")
        merged_sq+=sq;merged_count+=cnt
        directional.append({"offset_xyz":[dx,dy,dz],
                            "undirected_neighbor_pairs":cnt,
                            "weighted_squared_difference_sum":sq,
                            "contrast":sq/cnt})
    avg=sum(d["contrast"] for d in directional)/len(directional)
    merged=merged_sq/merged_count
    if abs(avg-REF_AVG)>DIFFERENCE or abs(merged-REF_MRG)>DIFFERENCE:
        raise ValueError("Official IBSI math disagrees with 3D avg or merged contrast references")
    return {"status":"PASS_OFFICIAL_IBSI_3D_AVG_AND_MERGED_MATH",
            "official_3d_avg_reference":REF_AVG,
            "original_3d_avg_direct":avg,
            "official_3d_merged_reference":REF_MRG,
            "original_3d_merged_direct":merged,
            "direction_count":len(directional),
            "roi_voxels":ROI,
            "undirected_pair_total":merged_count,
            "source_gray_levels":[1,3,4,6],
            "directional_detail":directional,
            "software":"stdlib_only_no_radiomics_package",
            "HCC_14_case_clinical_eligible_n":"NOT_ASSESSED",
            "MRI_RNA_associations_run":False,
            "IBSI_full_standard_claim":False}

def offline_test():
    assert len([d for d in itertools.product((-1,0,1),repeat=3) if d>(0,0,0)])==13
    assert value(tuple(range(80)),4,3,3)==79
    img=[1]*80;msk=[1]*80
    # A non-official altered phantom must fail
    try:compute(img,msk)
    except ValueError:pass
    else:raise AssertionError("Altered mask/phantom accepted")
    print("IBSI_ORIGINAL_DIGITAL_PHANTOM_3D_GLCM_STD_LIB_REFERENCE_OFFLINE_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--repo-dir",default="artifacts/ibsi_original_repo")
    ap.add_argument("--out-dir",default="artifacts/hcc_ibsi_independent")
    a=ap.parse_args()
    if a.offline_test:return offline_test()
    img,mask=find_original_files(a.repo_dir)
    report={**source_info(a.repo_dir),**compute(voxels(img),voxels(mask))}
    report["checked_at_utc"]=datetime.now(timezone.utc).isoformat()
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"hcc_ibsi1_official_independent_reference.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (out/"hcc_ibsi1_directional_glcm.csv").open(
        "w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=("dx","dy","dz","pairs","squared_difference_sum","contrast"))
        w.writeheader()
        for d in report["directional_detail"]:
            w.writerow({"dx":d["offset_xyz"][0],"dy":d["offset_xyz"][1],
                        "dz":d["offset_xyz"][2],
                        "pairs":d["undirected_neighbor_pairs"],
                        "squared_difference_sum":d["weighted_squared_difference_sum"],
                        "contrast":d["contrast"]})
    print(json.dumps({k:v for k,v in report.items() if k!="directional_detail"},ensure_ascii=False))
if __name__=="__main__":main()
