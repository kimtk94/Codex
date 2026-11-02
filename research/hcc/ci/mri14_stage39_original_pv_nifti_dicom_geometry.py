#!/usr/bin/env python3
"""HCC Stage39: original PV NIfTI header vs original DICOM source-series geometry.

14 original LiverHccSeg PV images are referenced by frozen patient ID, and
compared only at dimensions/physical pixel-spacing/slice counts to the 247
Stage38 original source DICOM per-directory header samples. Geometry is NOT a
pixel-wise or anatomic source-identity proof: potential matches remain REVIEW.
Never promote an index lesion, treatment chronology, or GDC RNA tissue origin.
"""
import argparse,csv,gzip,hashlib,io,json,math,os,re,struct
from collections import Counter,defaultdict
from itertools import combinations
from pathlib import Path
from zipfile import ZipFile
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from mri14_stage36_original_dicom_source_directory import patient,is_dicom_candidate,cases,ARCHIVE
from zenodo_nifti_zip_inventory import ARCHIVE as NIFTI_ARCHIVE,is_apple_sidecar

FIELDS=("patient_id","frozen_index_tumor","source_PV_nifti_archive_member",
        "source_PV_nifti_sha256","source_PV_header_dimension_xyz",
        "source_PV_header_spacing_xyz_mm","source_PV_NIfTI_source_status",
        "source_DICOM_directory","source_DICOM_SeriesInstanceUID",
        "source_DICOM_SeriesDescription","source_DICOM_series_instance_files",
        "source_DICOM_Rows","source_DICOM_Columns","source_DICOM_PixelSpacing",
        "stage38_textual_venous_candidate",
        "inplane_shape_compatible","inplane_pixel_spacing_compatible",
        "source_DICOM_slice_count_compatible",
        "source_geometry_evidence_class",
        "original_selected_PV_exact_DICOM_series_verified",
        "MRI_pre_HCC_treatment","RNA_same_frozen_index_tumor",
        "clinical_eligible","biology_tests","claim_ceiling")
PAT_FIELDS=("patient_id","original_PV_source_nifti_header","sampled_source_series",
           "unique_original_DICOM_series_UIDs","shape_compatible_series",
           "pixel_spacing_and_shape_compatible_series","geometry_3way_compatible_series",
           "geometry_3way_compatible_venous_labeled_series",
           "source_series_candidates_nonunique",
           "selected_PV_series_verified","clinical_eligibility",
           "MRI_RNA_tests","claim_ceiling")

def ensure(b,msg):
    if not b:raise ValueError(msg)

def csv_load(p):
    with Path(p).open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def nifti_header(data):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        h=f.read(352)
    ensure(len(h)==352 and h[344:348]==b"n+1\x00",
           "SOURCE_NIFTI1_GZIP_HEADER_NOT_VERIFIED")
    ensure(struct.unpack_from("<I",h,0)[0]==348,"NIFTI_HEADER_ENDIAN_OR_VERSION_UNSUPPORTED")
    d=struct.unpack_from("<8h",h,40)
    ensure(d[0]==3,"SOURCE_PV_NIFTI_NOT_3D")
    shape=tuple(int(v) for v in d[1:4])
    ensure(all(1<=v<=2048 for v in shape),"BAD_PV_NIFTI_SHAPE")
    pix=struct.unpack_from("<8f",h,76)
    spacing=tuple(float(abs(v)) for v in pix[1:4])
    ensure(all(math.isfinite(v) and 0.01<=v<100 for v in spacing),
           "BAD_SOURCE_PV_NIFTI_HEADER_SPACING")
    return shape,spacing

def number_pair(raw):
    found=re.findall(r"(?<![0-9a-zA-Z])(?:[0-9]+(?:[.][0-9]+)?)(?![0-9a-zA-Z])",
                     str(raw))
    if len(found)!=2:return None
    values=tuple(float(v) for v in found)
    return values if all(math.isfinite(x) and x>0 for x in values) else None

def geom(dcm,shape,spacing,nfiles):
    try:
        rr=int(dcm["Rows"]);cc=int(dcm["Columns"])
        if rr<=0 or cc<=0:raise ValueError("bad dimensions")
        p=number_pair(dcm["PixelSpacing"])
    except (ValueError,KeyError,TypeError):
        return "NO","NO","NO","UNRESOLVED_SOURCE_DICOM_MATRIX"
    orientations=[]
    for a,b in combinations(range(3),2):
        if sorted((rr,cc))==sorted((shape[a],shape[b])):
            vals=[(rr,cc),(cc,rr)]
            pixel_close=False
            for u,v in vals:
                if u==shape[a] and v==shape[b] and p:
                    # The DICOM pixel spacing is row/column; the exact NIfTI
                    # axis mapping is unknown, so allow either in-plane order.
                    for q in (p,p[::-1]):
                        tol=max(0.05,0.06*max(q))
                        if abs(q[0]-spacing[a])<=tol and abs(q[1]-spacing[b])<=tol:
                            pixel_close=True
            other=({0,1,2}-{a,b}).pop()
            orientations.append((pixel_close,nfiles==shape[other]))
    if not orientations:
        return "NO","NO","NO","SOURCE_MATRIX_DIMENSIONS_MISMATCH_REVIEW"
    has_sp=any(o[0] for o in orientations)
    has_slices=any(o[1] for o in orientations)
    both=any(o[0] and o[1] for o in orientations)
    if both:status="MATRIX_SPACING_INSTANCE_COUNT_COMPATIBLE_NOT_IDENTITY"
    elif has_sp:status="MATRIX_SPACING_COMPATIBLE_SLICE_COUNT_REVIEW"
    elif has_slices:status="MATRIX_SLICE_COUNT_COMPATIBLE_SPACING_REVIEW"
    else:status="MATRIX_COMPATIBLE_ONLY_REVIEW"
    return "YES","YES" if has_sp else "NO","YES" if has_slices else "NO",status

def source_pv(z,pid):
    candidates=[i for i in z.infolist() if not i.is_dir() and
                not is_apple_sidecar(i.filename) and
                patient(i.filename)==pid and
                i.filename.lower().split("/")[-1]=="pv.nii.gz"]
    ensure(len(candidates)==1,"SOURCE_PV_NIFTI_MEMBER_NOT_UNIQUE_OR_MISSING:"+pid)
    info=candidates[0]
    data=get_member_with_ranges(NIFTI_ARCHIVE,info,z.fp.total)
    return info.filename,hashlib.sha256(data).hexdigest(),*nifti_header(data)

def archive_folder_counts():
    by=Counter()
    with ZipFile(HTTPRangeFile(ARCHIVE)) as z:
        for info in z.infolist():
            if info.is_dir() or info.file_size<132 or
               not is_dicom_candidate(info.filename):continue
            pid=patient(info.filename)
            if pid:by[(pid,str(Path(info.filename).parent))]+=1
    return by

def run(rows,output):
    originals=cases()
    ensure(len(originals)==14,"FROZEN_14_CASE_UNIVERSE_MISSING")
    observed=defaultdict(list)
    for r in rows:
        pid=r["patient_id"]
        ensure(pid in originals,"SOURCE_SERIES_FOREIGN_PATIENT")
        ensure(r["status"].startswith("PASS_"),"STAGE38_SOURCE_HEADER_NOT_PASS")
        ensure(r["candidate_is_original_selected_PV"]=="NOT_ASSESSED" and
               r["clinical_eligibility"]=="NOT_ASSESSED",
               "SOURCE_38_ALREADY_FALSE_SELECTED_PV_CLINICAL_PROMOTION")
        observed[pid].append(r)
    ensure(set(observed)==set(originals),"STAGE38_SOURCE_SERIES_MISSING_FROZEN_CASE")
    counts=archive_folder_counts()
    case_rows=[];allrows=[];hold=[]
    with ZipFile(HTTPRangeFile(NIFTI_ARCHIVE)) as z:
        for pid in sorted(originals):
            match=observed[pid]
            nifname,digest,shape,spacing=source_pv(z,pid)
            eligible=[]
            for r in match:
                folder=r["source_directory"]
                nfiles=counts.get((pid,folder),0)
                ensure(nfiles>=1,"STAGE38_DICOM_SOURCE_DIRECTORY_NOT_IN_ORIGINAL_ZIP")
                dims=(r["Rows"],r["Columns"],r["PixelSpacing"])
                mat,sp,sl,cls=geom(r,shape,spacing,nfiles)
                isven=r["contrast_phase_header_candidate"]=="EXPLICIT_VENOUS_TEXT_CANDIDATE_UNVERIFIED"
                row=dict(
                  patient_id=pid,frozen_index_tumor=originals[pid]["representative_tumor_number"],
                  source_PV_nifti_archive_member=nifname,
                  source_PV_nifti_sha256=digest,
                  source_PV_header_dimension_xyz="x".join(map(str,shape)),
                  source_PV_header_spacing_xyz_mm="x".join(f"{v:.6g}" for v in spacing),
                  source_PV_NIfTI_source_status="PASS_CRC_ORIGINAL_PV_HEADER_ONLY",
                  source_DICOM_directory=folder,
                  source_DICOM_SeriesInstanceUID=r["SeriesInstanceUID"],
                  source_DICOM_SeriesDescription=r["SeriesDescription"],
                  source_DICOM_series_instance_files=nfiles,
                  source_DICOM_Rows=dims[0],source_DICOM_Columns=dims[1],
                  source_DICOM_PixelSpacing=dims[2],
                  stage38_textual_venous_candidate="YES" if isven else "NO",
                  inplane_shape_compatible=mat,
                  inplane_pixel_spacing_compatible=sp,
                  source_DICOM_slice_count_compatible=sl,
                  source_geometry_evidence_class=cls,
                  original_selected_PV_exact_DICOM_series_verified="NOT_ASSESSED",
                  MRI_pre_HCC_treatment="NOT_ASSESSED",
                  RNA_same_frozen_index_tumor="NOT_ASSESSED",
                  clinical_eligible="NOT_ASSESSED",
                  biology_tests=0,claim_ceiling="S0")
                allrows.append(row);eligible.append(row)
            tri=[r for r in eligible if r["source_geometry_evidence_class"]==
                 "MATRIX_SPACING_INSTANCE_COUNT_COMPATIBLE_NOT_IDENTITY"]
            case_rows.append(dict(
              patient_id=pid,original_PV_source_nifti_header="PASS_CRC_ORIGINAL_SOURCE",
              sampled_source_series=len(match),
              unique_original_DICOM_series_UIDs=len({r["SeriesInstanceUID"] for r in match}),
              shape_compatible_series=sum(r["inplane_shape_compatible"]=="YES" for r in eligible),
              pixel_spacing_and_shape_compatible_series=sum(r["inplane_shape_compatible"]=="YES" and
                                                     r["inplane_pixel_spacing_compatible"]=="YES" for r in eligible),
              geometry_3way_compatible_series=len(tri),
              geometry_3way_compatible_venous_labeled_series=sum(
                   r["stage38_textual_venous_candidate"]=="YES" for r in tri),
              source_series_candidates_nonunique="YES" if len(tri)>1 else "NO",
              selected_PV_series_verified="NOT_ASSESSED",
              clinical_eligibility="NOT_ASSESSED",MRI_RNA_tests=0,claim_ceiling="S0"))
            print("HCC_STAGE39_PATIENT_PV_GEOMETRY",pid,
                  "pv_shape",shape,"source_series",len(match),
                  "matrix",case_rows[-1]["shape_compatible_series"],
                  "3way",len(tri),flush=True)
    ensure(len(case_rows)==14 and len(allrows)==len(rows),"STAGE39_SOURCE_GEOMETRY_CASE_LOSS")
    summary=dict(
      stage="HCC_STAGE39_OFFICIAL_PV_NIFTI_VS_SOURCE_DICOM_GEOMETRY",
      frozen_tcga_lihc_mri14=14,original_PV_NIfTI_source_headers_verified=14,
      stage38_original_source_DICOM_headers_compared=len(rows),
      original_DICOM_source_directories_covered=len(counts),
      source_matrix_compatible_rows=sum(r["inplane_shape_compatible"]=="YES" for r in allrows),
      source_inplane_matrix_and_spacing_compatible_rows=sum(
          r["inplane_shape_compatible"]=="YES" and
          r["inplane_pixel_spacing_compatible"]=="YES" for r in allrows),
      source_3way_geometry_compatible_rows=sum(r["source_geometry_evidence_class"]==
          "MATRIX_SPACING_INSTANCE_COUNT_COMPATIBLE_NOT_IDENTITY" for r in allrows),
      patients_with_at_least_one_3way_geometry_candidate=sum(int(r["geometry_3way_compatible_series"])>0 for r in case_rows),
      patients_with_multiple_3way_geometry_candidates=sum(r["source_series_candidates_nonunique"]=="YES" for r in case_rows),
      original_selected_PV_DICOM_series_pixel_identity_verified_n=0,
      authoritative_MRI_before_HCC_therapy_n=0,
      exact_RNA_sample_same_MRI_index_tumor_n=0,
      clinical_eligible_n="NOT_ASSESSED",
      MRI_RNA_biological_tests=0,claim_ceiling="S0",
      source_whole_Zenodo_ZIP_MD5_independently_verified=False,
      geometry_proves_original_selected_DICOM_series=False,
      decision="NIFTI_DICOM_GEOMETRY_CANDIDATE_QC_ONLY_NO_PIXEL_IDENTITY_NO_CLINICAL_GO")
    output.mkdir(parents=True,exist_ok=True)
    def write(path,cols,data):
        with (output/path).open("w",newline="",encoding="utf8") as f:
            w=csv.DictWriter(f,fieldnames=cols)
            w.writeheader();w.writerows(data)
    write("stage39_source_14patient_PV_geometry_priority.csv",PAT_FIELDS,case_rows)
    write("stage39_source_247_DICOM_series_to_PV_NIfTI_geometry.csv",FIELDS,allrows)
    (output/"stage39_original_source_NIfTI_DICOM_geometry_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    lines=["# HCC Stage39 source DICOM vs native PV NIfTI geometry",
      "","14 frozen cases; original PV NIfTI CRC and raw header verified. Geometry is not source pixel-identity.",
      "Cases with at least one three-way geometry candidate: "+
      str(summary["patients_with_at_least_one_3way_geometry_candidate"])+"/14",
      "Patients with >1 compatible candidate: "+
      str(summary["patients_with_multiple_3way_geometry_candidates"])+"/14",
      "Selected native portal-venous series UID proof 0/14; same index tumor RNA and pretreatment source HOLD.",
      "MRI–RNA 0/12 tests and claim ceiling S0.","",
      "| Patient | Source DICOM series sampled | Matrix compatible | Matrix + spacing compatible | Geometry three-way candidate |",
      "|---|---:|---:|---:|---:|"]
    for row in case_rows:
        lines.append("| "+row["patient_id"]+" | "+str(row["sampled_source_series"])+" | "+
          str(row["shape_compatible_series"])+" | "+
          str(row["pixel_spacing_and_shape_compatible_series"])+" | "+
          str(row["geometry_3way_compatible_series"])+" |")
    report="\n".join(lines)+"\n"
    (output/"stage39_source_NIfTI_DICOM_geometry_report.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE39_OFFICIAL_NATIVE_PV_SOURCE_GEOMETRY_GUARD",
          json.dumps(summary,sort_keys=True),flush=True)

def tests():
    a={"Rows":"512","Columns":"512","PixelSpacing":"0.7|0.7"}
    assert geom(a,(512,512,90),(0.7,0.7,3),90)[3]=="MATRIX_SPACING_INSTANCE_COUNT_COMPATIBLE_NOT_IDENTITY"
    assert geom(a,(512,512,90),(0.7,0.7,3),42)[3]=="MATRIX_SPACING_COMPATIBLE_SLICE_COUNT_REVIEW"
    assert geom(a,(256,256,90),(0.7,0.7,3),90)[3]=="SOURCE_MATRIX_DIMENSIONS_MISMATCH_REVIEW"
    assert geom(a,(512,512,90),(0.7,0.7,3),90)[0]=="YES"
    assert number_pair("0.7|0.7")==(.7,.7)
    print("HCC_STAGE39_ORIGINAL_SOURCE_DIM_SPACING_COUNT_NEGATIVE_TEST_PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage38-csv",type=Path)
    ap.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage39_native_source_geometry"))
    ap.add_argument("--offline-test",action="store_true")
    args=ap.parse_args()
    tests()
    if args.offline_test:return
    ensure(args.stage38_csv and args.stage38_csv.is_file(),"STAGE38_FROZEN_ORIGINAL_SOURCE_CSV_REQUIRED")
    run(csv_load(args.stage38_csv),args.out_dir)
if __name__=="__main__":main()
