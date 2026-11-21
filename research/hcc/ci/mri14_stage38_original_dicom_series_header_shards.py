#!/usr/bin/env python3
"""HCC Stage38: independently inventory original DICOM series-header candidates.

The original Zenodo 8179129 dicoms.zip has >36k files. We read at most one
DICOM instance per *distinct source directory*, bounded by deterministic
alphabetical selection before reading clinical or MRI/RNA outcomes.
4 disjoint patient shards (14 original frozen TCGA cases), HTTP byte ranges
with ZIP member CRC, only DICOM headers; NEVER compare shifted DICOM dates to
GDC relative days or infer which specific MRI index-lesion scan was sampled.
An explicit PV-like source SeriesDescription is a CANDIDATE, not a validated
selected PV NIfTI or tumor / GDC RNA match.
"""
import argparse,csv,io,json,os,re,hashlib
from pathlib import Path
from collections import defaultdict,Counter
from zipfile import ZipFile
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from mri14_stage36_original_dicom_source_directory import (
    ARCHIVE, ORIGINAL_DECLARED_MD5, patient, is_dicom_candidate, cases
)
from mri14_stage37_original_dicom_source_header_probe import dicom_header,evaluate_header

MAX_SOURCE_MEMBER=24*1024*1024
FIELDS=("patient_id","source_directory","original_source_member",
        "member_size_bytes","member_crc_verified","member_sha256",
        "PatientID","Modality","StudyInstanceUID","SeriesInstanceUID",
        "SOPInstanceUID","SeriesNumber","SeriesDescription","ProtocolName",
        "ImageType","Rows","Columns","MagneticFieldStrength",
        "MRAcquisitionType","SequenceName","PixelSpacing","SliceThickness",
        "SpacingBetweenSlices","contrast_phase_header_candidate",
        "candidate_is_original_selected_PV","same_mri_index_lesion_GDC_RNA",
        "clinical_eligibility","status")
PAT_FIELDS=("patient_id","frozen_index_tumor","source_dicom_directories_total",
            "source_directories_sampled","source_directories_not_sampled_cap",
            "valid_MR_series_UID_samples","distinct_study_uids","distinct_series_uids",
            "source_explicit_venous_header_candidates","source_arterial_header_candidates",
            "source_other_header_candidates","source_unclassified_header_candidates",
            "source_header_error_rows","original_selected_PV_series_identity",
            "clinical_pretherapy_verification","RNA_same_index_lesion",
            "clinical_eligible","MRI_RNA_biology_tests","claim_ceiling")
VN=re.compile(r"(?i)(?:^|[^a-z0-9])(?:portal[ -]?venous|venous|portal|p[._ -]?v)(?:[^a-z0-9]|$)")
ART=re.compile(r"(?i)(?:^|[^a-z0-9])(?:arterial|art|hepatic[ -]?artery)(?:[^a-z0-9]|$)")
OTHER=re.compile(r"(?i)(?:^|[^a-z0-9])(?:diffusion|dwi|adc|t2w?|t1[ -]?pre|non[ -]?contrast|plain|precontrast|pre[ -]?contrast|delayed|delay|equilibrium|hepatobiliary|hbp)(?:[^a-z0-9]|$)")

def must(ok,msg):
    if not ok:raise ValueError(msg)

def classify(h):
    # Only a source *textual candidate*, never a unique phase conclusion.
    s=" ".join([h.get("SeriesDescription",""),h.get("ProtocolName","")])
    isv=bool(VN.search(s)); isa=bool(ART.search(s)); iso=bool(OTHER.search(s))
    if isv and (isa or iso):return "CONFLICTING_PHASE_LABELS_HOLD"
    if isv:return "EXPLICIT_VENOUS_TEXT_CANDIDATE_UNVERIFIED"
    if isa:return "ARTERIAL_TEXT_NOT_SELECTED_PV"
    if iso:return "OTHER_SEQUENCE_TEXT_NOT_SELECTED_PV"
    return "UNCLASSIFIED_SOURCE_SEQUENCE"

def eligible_members(z,ids):
    by=defaultdict(lambda:defaultdict(list))
    for i in z.infolist():
        if i.is_dir() or i.file_size<132 or i.file_size>MAX_SOURCE_MEMBER:continue
        pid=patient(i.filename)
        if pid in ids and is_dicom_candidate(i.filename):
            by[pid][str(Path(i.filename).parent)].append(i)
    return by

def header_extra(data):
    import pydicom
    ds=pydicom.dcmread(io.BytesIO(data),stop_before_pixels=True,force=False)
    def clean(v):
        if isinstance(v,(list,tuple)):return "|".join(str(x) for x in v)[:170]
        return str(v or "")[:170]
    return {k:clean(getattr(ds,k,"")) for k in (
        "MagneticFieldStrength","MRAcquisitionType","SequenceName",
        "PixelSpacing","SliceThickness","SpacingBetweenSlices")}

def run_shard(shard,shards,max_folders):
    allcases=cases()
    mine={p:allcases[p] for i,p in enumerate(sorted(allcases)) if i%shards==shard}
    must(mine,"EMPTY_PATIENT_SHARD")
    rows=[];summary=[];fails=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as z:
        inventory=eligible_members(z,set(mine))
        for pid,meta in sorted(mine.items()):
            folders=inventory[pid]
            ordered=sorted(folders)
            source_count=len(ordered)
            sampled=ordered[:max_folders]
            valid=[];case_rows=[]
            for folder in sampled:
                info=min(folders[folder],key=lambda x:x.filename)
                row={k:"" for k in FIELDS}
                row.update({
                    "patient_id":pid,"source_directory":folder,
                    "original_source_member":info.filename,
                    "member_size_bytes":info.file_size,
                    "member_crc_verified":"NO",
                    "contrast_phase_header_candidate":"NOT_EVALUATED",
                    "candidate_is_original_selected_PV":"NOT_ASSESSED",
                    "same_mri_index_lesion_GDC_RNA":"NOT_ASSESSED",
                    "clinical_eligibility":"NOT_ASSESSED"})
                try:
                    data=get_member_with_ranges(ARCHIVE,info,z.fp.total)
                    row["member_crc_verified"]="YES"
                    row["member_sha256"]=hashlib.sha256(data).hexdigest()
                    h=dicom_header(data); h.update(header_extra(data))
                    good,status=evaluate_header(h,pid)
                    for k in h:
                        if k in row:row[k]=h[k]
                    row["status"]=status
                    if status.startswith("PASS_"):
                        row["contrast_phase_header_candidate"]=classify(h)
                        valid.append(row)
                    else:
                        fails.append((pid,folder,status))
                except Exception as exc:
                    row["status"]="HOLD_DICOM_HEADER_"+type(exc).__name__
                    fails.append((pid,folder,row["status"]))
                case_rows.append(row)
                print("HCC_STAGE38_SHARD",shard,pid,
                      row["contrast_phase_header_candidate"],row["status"],flush=True)
            rows.extend(case_rows)
            c=Counter(x["contrast_phase_header_candidate"] for x in valid)
            summary.append(dict(
              patient_id=pid,frozen_index_tumor=meta["representative_tumor_number"],
              source_dicom_directories_total=source_count,
              source_directories_sampled=len(sampled),
              source_directories_not_sampled_cap=source_count-len(sampled),
              valid_MR_series_UID_samples=len(valid),
              distinct_study_uids=len({r["StudyInstanceUID"] for r in valid}),
              distinct_series_uids=len({r["SeriesInstanceUID"] for r in valid}),
              source_explicit_venous_header_candidates=c["EXPLICIT_VENOUS_TEXT_CANDIDATE_UNVERIFIED"],
              source_arterial_header_candidates=c["ARTERIAL_TEXT_NOT_SELECTED_PV"],
              source_other_header_candidates=c["OTHER_SEQUENCE_TEXT_NOT_SELECTED_PV"],
              source_unclassified_header_candidates=c["UNCLASSIFIED_SOURCE_SEQUENCE"],
              source_header_error_rows=len(case_rows)-len(valid),
              original_selected_PV_series_identity="NOT_ASSESSED",
              clinical_pretherapy_verification="NOT_ASSESSED",
              RNA_same_index_lesion="NOT_ASSESSED",
              clinical_eligible="NOT_ASSESSED",MRI_RNA_biology_tests=0,claim_ceiling="S0"))
            print("HCC_STAGE38_PATIENT_HEADER_SUMMARY",pid,
                  "source_folders",source_count,"sampled",len(sampled),
                  "valid",len(valid),"venous_labels",c["EXPLICIT_VENOUS_TEXT_CANDIDATE_UNVERIFIED"],
                  flush=True)
    must(len(summary)==len(mine),"SOURCE_14_PATIENT_SHARD_COVERAGE_DRIFT")
    return rows,summary

def dump_csv(path,cols,rows):
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction="raise")
        w.writeheader();w.writerows(rows)

def shard_main(args):
    rows,patients=run_shard(args.shard,args.shards,args.max_folders)
    d=args.out_dir;d.mkdir(parents=True,exist_ok=True)
    dump_csv(d/("stage38_series_headers_shard"+str(args.shard)+".csv"),FIELDS,rows)
    dump_csv(d/("stage38_patient_summary_shard"+str(args.shard)+".csv"),PAT_FIELDS,patients)
    print("HCC_STAGE38_SHARD_COMPLETED",args.shard,len(patients),"cases",
          len(rows),"headers",flush=True)

def aggregate(args):
    d=args.out_dir
    headers=[];patients=[]
    for i in range(args.shards):
        fp=d/("stage38_series_headers_shard"+str(i)+".csv")
        pp=d/("stage38_patient_summary_shard"+str(i)+".csv")
        must(fp.is_file() and pp.is_file(),"MISSING_SOURCE_DICOM_SERIES_SHARD:"+str(i))
        for path,target in ((fp,headers),(pp,patients)):
            with path.open(newline="",encoding="utf8") as f:
                target.extend(csv.DictReader(f))
    ids=set(cases())
    must(len(patients)==14 and {x["patient_id"] for x in patients}==ids,
         "STAGE38_FROZEN_PATIENT_LIST_INCOMPLETE")
    must(len({x["patient_id"] for x in patients})==14,
         "STAGE38_DUPLICATE_PATIENT_IN_SHARDS")
    for r in patients:
        must(r["clinical_eligible"]=="NOT_ASSESSED" and
             r["original_selected_PV_series_identity"]=="NOT_ASSESSED" and
             r["RNA_same_index_lesion"]=="NOT_ASSESSED" and
             r["clinical_pretherapy_verification"]=="NOT_ASSESSED" and
             r["claim_ceiling"]=="S0" and int(r["MRI_RNA_biology_tests"])==0,
             "UNSUPPORTED_CLINICAL_SOURCE_PROMOTION")
        must(int(r["source_directories_sampled"])<=args.max_folders,
             "SRC_DICOM_BOUNDED_SERIES_CAP_VIOLATION")
    totals=dict(
       stage="HCC_STAGE38_OFFICIAL_DICOM_SOURCE_SERIES_HEADER_SHARDED",
       zenodo_source="https://zenodo.org/records/8179129",
       frozen_patient_denominator=14,
       patients_with_original_source_directory_candidates=sum(int(x["source_dicom_directories_total"])>0 for x in patients),
       patients_with_at_least_one_valid_original_MR_series_UID=sum(int(x["valid_MR_series_UID_samples"])>0 for x in patients),
       patients_with_explicit_venous_text_header_candidate=sum(int(x["source_explicit_venous_header_candidates"])>0 for x in patients),
       original_source_directories_total=sum(int(x["source_dicom_directories_total"]) for x in patients),
       original_source_directory_sample_count=len(headers),
       source_directories_not_sampled_due_to_cap=sum(int(x["source_directories_not_sampled_cap"]) for x in patients),
       source_header_valid_samples=sum(int(x["valid_MR_series_UID_samples"]) for x in patients),
       header_explicit_venous_candidate_rows=sum(int(x["source_explicit_venous_header_candidates"]) for x in patients),
       source_header_error_rows=sum(int(x["source_header_error_rows"]) for x in patients),
       source_selected_PV_series_confirmed=0,
       source_selected_PV_NIfTI_voxel_compatible_confirmed=0,
       MRI_before_HCC_treatment_confirmed=0,
       RNA_same_index_tumor_confirmed=0,
       independent_radiologist_approved_n=0,
       clinical_eligible_n="NOT_ASSESSED",
       MRI_RNA_biological_tests=0,claim_ceiling="S0",
       original_source_archive_whole_MD5_not_verified=True,
       selected_source_series_not_determined_from_text_only=True,
       decision="SOURCE_DICOM_SERIES_HEADER_CANDIDATE_DISCOVERY_ONLY_CLINICAL_HOLD")
    dump_csv(d/"stage38_original14_source_DICOM_series_header_inventory.csv",FIELDS,headers)
    dump_csv(d/"stage38_original14_patient_source_series_priority.csv",PAT_FIELDS,patients)
    (d/"stage38_original14_DICOM_series_header_source_summary.json").write_text(
        json.dumps(totals,indent=2)+"\n",encoding="utf8")
    lines=["# HCC Stage38: original DICOM series header candidate inventory",
      "", "One original CRC-checked DICOM instance per source directory, deterministic alphabetical",
      "within frozen TCGA patient, first "+str(args.max_folders)+" directories per patient.",
      "Total distinct directories: "+str(totals["original_source_directories_total"]),
      "Actual sampled source series headers: "+str(totals["source_header_valid_samples"]),
      "Patients with explicit venous-like textual header candidate: "+
      str(totals["patients_with_explicit_venous_text_header_candidate"])+"/14.",
      "Candidate Phase text is NOT validation of selected portal-venous NIfTI.",
      "No case-level MRI-before-HCC-treatment, same index-tumor RNA specimen,",
      "or expert independent anatomy evidence. Eligibility NOT_ASSESSED, 0/12 tests S0.","",
      "| Case | Source folders | Sampled | Venous-text candidates | Unclassified |",
      "|---|---:|---:|---:|---:|"]
    for p in patients:
        lines.append("| "+p["patient_id"]+" | "+p["source_dicom_directories_total"]+
          " | "+p["source_directories_sampled"]+" | "+
          p["source_explicit_venous_header_candidates"]+" | "+
          p["source_unclassified_header_candidates"]+" |")
    report="\n".join(lines)+"\n"
    (d/"stage38_source_series_header_candidate_report.md").write_text(report,encoding="utf8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE38_ORIGINAL14_SHARDED_SOURCE_SERIES_HEADERS_AGGREGATED",
          json.dumps(totals,sort_keys=True),flush=True)

def offline_test():
    b={"PatientID":"TCGA-BC-A10Y","Modality":"MR","StudyInstanceUID":"1.2.3",
       "SeriesInstanceUID":"1.2.4","SOPInstanceUID":"1.2.5"}
    assert classify(dict(b,SeriesDescription="Portal venous",ProtocolName=""))=="EXPLICIT_VENOUS_TEXT_CANDIDATE_UNVERIFIED"
    assert classify(dict(b,SeriesDescription="DWI",ProtocolName=""))=="OTHER_SEQUENCE_TEXT_NOT_SELECTED_PV"
    assert classify(dict(b,SeriesDescription="ART",ProtocolName=""))=="ARTERIAL_TEXT_NOT_SELECTED_PV"
    assert classify(dict(b,SeriesDescription="ART PV",ProtocolName=""))=="CONFLICTING_PHASE_LABELS_HOLD"
    assert classify(dict(b,SeriesDescription="",ProtocolName=""))=="UNCLASSIFIED_SOURCE_SEQUENCE"
    assert len(cases())==14
    print("HCC_STAGE38_5_ORIGINAL_SERIES_PHASE_TEXT_NEGATIVE_FIXTURES_PASS")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--shards",type=int,default=4)
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--max-folders",type=int,default=16)
    a.add_argument("--aggregate",action="store_true")
    a.add_argument("--offline-test",action="store_true")
    a.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage38_source_series"))
    opt=a.parse_args()
    offline_test()
    must(opt.shards==4 and 0<=opt.shard<opt.shards and 1<=opt.max_folders<=32,
         "STAGE38_BOUNDED_SHARD_CONFIGURATION_INVALID")
    if opt.offline_test:return
    if opt.aggregate:aggregate(opt)
    else:shard_main(opt)
if __name__=="__main__":main()
