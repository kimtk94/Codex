#!/usr/bin/env python3
"""HCC Stage37: original Zenodo DICOM header sample, one source image per TCGA-LIHC case.

Only public original LiverHccSeg v1.1 dicoms.zip selected ZIP members are read
with bounded HTTP byte-range calls, verifying each ZIP member CRC. Does not
download entire source ZIP, verify whole ZIP MD5, or identify the indexed
PV scan from one unselected DICOM series. Extract first eligible member
alphabetically by archive path per patient without outcome-based selection.
Clinical pretreatment, exact tumor RNA, expert anatomy and 12 biological tests
remain UNVERIFIED / NOT EXECUTED.
"""
import argparse,csv,hashlib,io,json,os,re
from pathlib import Path
from zipfile import ZipFile
from mri_mask_voxel_audit import HTTPRangeFile
from fast_zip_member_range import get_member_with_ranges
from mri14_stage36_original_dicom_source_directory import (
    ARCHIVE,ORIGINAL_DECLARED_MD5,patient,is_dicom_candidate,cases
)

MAX_SAMPLE=32*1024*1024
UID=re.compile(r"(?:[0-9]+[.])+[0-9]+")
COLUMNS=("patient_id","source_DICOM_member_path","source_ZIP_member_bytes",
  "source_ZIP_member_crc32_verified","source_DICOM_sha256",
  "source_DICOM_patient_id","source_DICOM_patient_id_matches_frozen_TCGA_case",
  "source_DICOM_Modality","source_DICOM_StudyInstanceUID","source_DICOM_SeriesInstanceUID",
  "source_DICOM_SOPInstanceUID","source_DICOM_SeriesDescription",
  "source_DICOM_ProtocolName","source_DICOM_SeriesNumber","source_DICOM_ImageType",
  "source_DICOM_Rows","source_DICOM_Columns",
  "source_DICOM_sample_status","original_PV_index_lesion_series_confirmed",
  "selected_mri_scan_before_relevant_HCC_therapy",
  "RNA_sample_same_index_lesion","eligible_radiogenomics",
  "MRI_RNA_tests","claim_ceiling")
HOLD_COLS=("patient_id","original_DICOM_path","reason","detail","clinical_eligibility")

def demand(ok,reason):
    if not ok:raise ValueError(reason)

def dicom_header(data):
    import pydicom
    ds=pydicom.dcmread(io.BytesIO(data),stop_before_pixels=True,force=False)
    def field(k):
        x=getattr(ds,k,"")
        if isinstance(x,(list,tuple)):
            x="|".join(str(v) for v in x)
        return str(x or "").strip()[:350]
    return {x:field(x) for x in (
       "PatientID","Modality","StudyInstanceUID","SeriesInstanceUID",
       "SOPInstanceUID","SeriesDescription","ProtocolName","SeriesNumber",
       "ImageType","Rows","Columns")}

def evaluate_header(h,pid):
    study=h["StudyInstanceUID"];series=h["SeriesInstanceUID"]
    pat=h["PatientID"].strip().upper().replace("_","-")
    source_id_match=pat==pid
    valid_study=bool(UID.fullmatch(study)) and len(study)<=64
    valid_series=bool(UID.fullmatch(series)) and len(series)<=64
    valid_sop=bool(UID.fullmatch(h["SOPInstanceUID"])) and len(h["SOPInstanceUID"])<=64
    valid_mr=h["Modality"].upper()=="MR"
    if not source_id_match:status="HOLD_SOURCE_DICOM_PATIENT_ID_MISMATCH"
    elif not valid_mr:status="HOLD_ORIGINAL_IMAGE_NOT_MR"
    elif not (valid_study and valid_series and valid_sop):
        status="HOLD_ORIGINAL_DICOM_STUDY_SERIES_SOP_UID_INVALID"
    else:
        status="PASS_ORIGINAL_DICOM_HEADER_ONE_UNSELECTED_SERIES_SAMPLE_ONLY"
    return source_id_match,status

def get_one(z,pid):
    # Deliberately sample one source path per case WITHOUT choosing by MRI/RNA
    # feature, chronological order, lesion size, phase or clinically relevant data.
    candidates=sorted((x for x in z.infolist() if
                        not x.is_dir() and patient(x.filename)==pid and
                        is_dicom_candidate(x.filename) and
                        132<=x.file_size<=MAX_SAMPLE),
                      key=lambda x:x.filename)
    if not candidates:raise ValueError("NO_BOUNDED_DICOM_LIKE_SOURCE_INSTANCE")
    return candidates[0]

def analyze():
    by=cases()
    out=[];holds=[]
    with ZipFile(HTTPRangeFile(ARCHIVE)) as archive:
        for pid in sorted(by):
            name=""
            try:
                info=get_one(archive,pid);name=info.filename
                data=get_member_with_ranges(ARCHIVE,info,archive.fp.total)
                digest=hashlib.sha256(data).hexdigest()
                header=dicom_header(data)
                matched,status=evaluate_header(header,pid)
                row={
                  "patient_id":pid,"source_DICOM_member_path":name,
                  "source_ZIP_member_bytes":info.file_size,
                  "source_ZIP_member_crc32_verified":"YES",
                  "source_DICOM_sha256":digest,
                  "source_DICOM_patient_id":header["PatientID"],
                  "source_DICOM_patient_id_matches_frozen_TCGA_case":"YES" if matched else "NO",
                  **{"source_DICOM_"+k:header[k] for k in ("Modality","StudyInstanceUID",
                      "SeriesInstanceUID","SOPInstanceUID","SeriesDescription","ProtocolName",
                      "SeriesNumber","ImageType","Rows","Columns")},
                  "source_DICOM_sample_status":status}
                if status.startswith("HOLD"):
                    holds.append({"patient_id":pid,"original_DICOM_path":name,
                                  "reason":status,"detail":"Original source header cannot qualify single sampled series",
                                  "clinical_eligibility":"NOT_ASSESSED"})
            except Exception as exc:
                row={"patient_id":pid,"source_DICOM_member_path":name,
                     "source_DICOM_sample_status":"HOLD_SOURCE_DICOM_READ_"+type(exc).__name__}
                holds.append({"patient_id":pid,"original_DICOM_path":name,
                              "reason":type(exc).__name__,"detail":str(exc)[:250],
                              "clinical_eligibility":"NOT_ASSESSED"})
            row.update({
              "original_PV_index_lesion_series_confirmed":"NOT_ASSESSED",
              "selected_mri_scan_before_relevant_HCC_therapy":"NOT_ASSESSED",
              "RNA_sample_same_index_lesion":"NOT_ASSESSED",
              "eligible_radiogenomics":"NOT_ASSESSED",
              "MRI_RNA_tests":0,"claim_ceiling":"S0"})
            out.append(row)
            print("HCC_STAGE37_ORIGINAL_SINGLE_DICOM_HEADER_CASE",
                  pid,row["source_DICOM_sample_status"],
                  flush=True)
    demand(len(out)==14 and len({r["patient_id"] for r in out})==14,
           "ORIGINAL_SOURCE_14_CASES_INCOMPLETE")
    return out,holds

def write(out,rows,holds):
    from collections import Counter
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stage37_original14_one_DICOM_header_sample.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS);w.writeheader();w.writerows(rows)
    with (out/"stage37_original14_DICOM_header_HOLD.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=HOLD_COLS);w.writeheader();w.writerows(holds)
    counted=Counter(r["source_DICOM_sample_status"] for r in rows)
    passed=counted["PASS_ORIGINAL_DICOM_HEADER_ONE_UNSELECTED_SERIES_SAMPLE_ONLY"]
    summary={
      "stage":"HCC_STAGE37_OFFICIAL_DICOM_SINGLE_SOURCE_HEADER_PER_PATIENT",
      "original_record":"https://zenodo.org/records/8179129",
      "source_archive_publisher_declared_md5":ORIGINAL_DECLARED_MD5,
      "full_original_source_ZIP_downloaded":False,
      "full_original_source_ZIP_md5_verified":False,
      "source_member_ZIP_CRC_checked":True,
      "patient_denominator":14,
      "source_original_DICOM_one_sample_per_patient":14,
      "source_DICOM_header_valid_sampled_patients":passed,
      "original_DICOM_source_header_HOLD_patients":len(holds),
      "source_DICOM_source_header_status":dict(counted),
      "source_exact_PV_selected_MRI_series_confirmed":0,
      "authoritative_MRI_before_HCC_treatment_confirmed":0,
      "same_MRI_index_tumor_to_GDC_RNA_aliquot_confirmed":0,
      "clinically_eligible_n":"NOT_ASSESSED",
      "MRI_RNA_biological_tests":0,
      "claim_ceiling":"S0",
      "source_only_result":"ORIGINAL_DICOM_ONE_SERIES_SAMPLE_NOT_SELECTED_PV_REPLICATION",
      "clinical_pairing_result":"HOLD"}
    (out/"stage37_original_DICOM_header_source_qc_summary.json").write_text(
       json.dumps(summary,indent=2)+"\n")
    lines=["# Stage37 — actual original DICOM header sampled once per frozen TCGA-LIHC MRI patient",
       "", "Original source Zenodo 8179129; one original source image per patient; ZIP member CRC checked.",
       "Whole archive was NOT downloaded; declared ZIP MD5 NOT independently verified.",
       "Valid original DICOM header for one unselected series: "+str(passed)+"/14.",
       "Source DICOM read/HOLD: "+str(len(holds))+"/14.",
       "No evidence selected portal-venous source series or exact same MRI-index tumor RNA aliquot.",
       "No source-authoritative patient MRI-before-HCC-treatment chronology. Clinical eligibility NOT_ASSESSED.",
       "No MRI-RNA tests (0/12); S0.","",
       "| Patient | Original DICOM header | Modality | Series number | Source series description |",
       "|---|---|---|---|---|"]
    for r in rows:
        lines.append("| "+r["patient_id"]+" | "+r["source_DICOM_sample_status"]+
          " | "+r.get("source_DICOM_Modality","")+" | "+r.get("source_DICOM_SeriesNumber","")+
          " | "+r.get("source_DICOM_SeriesDescription","").replace("|","/")[:65]+" |")
    report="\n".join(lines)+"\n"
    (out/"stage37_original_DICOM_source_header_report.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE37_SOURCE_DICOM_HEADER_RESULTS",json.dumps(summary,sort_keys=True),flush=True)

def offline():
    base={"PatientID":"TCGA-BC-A10Y","Modality":"MR",
          "StudyInstanceUID":"1.2.3.4","SeriesInstanceUID":"1.2.3.5",
          "SOPInstanceUID":"1.2.3.6"}
    assert evaluate_header(base,"TCGA-BC-A10Y")[1].startswith("PASS_")
    assert evaluate_header(base,"TCGA-DD-A4NF")[1].startswith("HOLD_")
    assert evaluate_header(dict(base,Modality="CT"),"TCGA-BC-A10Y")[1].startswith("HOLD_")
    assert evaluate_header(dict(base,SeriesInstanceUID="invalid"),"TCGA-BC-A10Y")[1].startswith("HOLD_")
    assert len(cases())==14
    print("HCC_STAGE37_DICOM_UID_PATIENT_MODALIY_FAIL_CLOSED_TESTS_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage37_original_dicom_header"))
    a=p.parse_args()
    offline()
    if a.offline_test:return
    rows,holds=analyze()
    write(a.out_dir,rows,holds)
if __name__=="__main__":main()
