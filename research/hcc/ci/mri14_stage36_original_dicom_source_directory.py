#!/usr/bin/env python3
"""HCC Stage36: official LiverHccSeg dicoms.zip source directory audit.

Read ZIP central directory with bounded HTTP ranges, never entire 1.7GB ZIP.
Count exact frozen 14 TCGA case path, DICOM-like members and venous filename
hints. No original DICOM header, source MRI-therapy timestamp mapping, or
tumor RNA anatomical provenance asserted from directory names alone.
"""
import argparse
import csv
import json
import os
import re
from pathlib import Path
from zipfile import ZipFile
from mri_mask_voxel_audit import HTTPRangeFile

ARCHIVE="https://zenodo.org/records/8179129/files/dicoms.zip?download=1"
ORIGINAL_DECLARED_MD5="1ff9f35e77d2892909dd2c67eea196b3"
FROZEN="research/hcc/HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
PAT=re.compile(r"TCGA[-_][A-Z0-9]{2}[-_][A-Z0-9]{4}",re.I)
VENOUS=re.compile(r"(?:^|[/_.-])(?:pv|venous|portal|portovenous)(?:[/_.-]|$)",re.I)
COLS=("patient_id","selected_tumor","original_dicom_archive_patient_members",
"original_dicom_candidate_members","venous_directory_name_hint_members",
"distinct_original_source_directories","source_dicom_example_paths",
"source_venous_example_paths","source_directory_status",
"StudyUID_from_original_DICOM_header","SeriesUID_from_original_DICOM_header",
"scan_before_HCC_therapy","RNA_same_index_tumor","clinical_eligibility",
"biology_tests","claim_ceiling")

def ensure(b,msg):
    if not b:raise ValueError(msg)

def patient(name):
    n=name.replace("\\","/")
    if n.startswith("__MACOSX/") or "/__MACOSX/" in n or "/._" in n:
        return ""
    found={m.group(0).upper().replace("_","-") for m in PAT.finditer(n)}
    return next(iter(found)) if len(found)==1 else ""

def is_dicom_candidate(name):
    n=Path(name).name.lower()
    if not n or n.startswith("."):return False
    ext=Path(n).suffix.lower()
    return ext in (".dcm",".dicom",".ima","") or ext.lstrip(".").isdigit()

def cases():
    with open(FROZEN,newline="",encoding="utf8") as f:rows=list(csv.DictReader(f))
    ensure(len(rows)==14 and len({r["patient_id"] for r in rows})==14,
           "FROZEN_14_SOURCE_COHORT_DRIFT")
    for row in rows:
        ensure(row["expert_review"]=="NOT_ASSESSED" and
               row["pretreatment_verified"]=="NOT_ASSESSED" and
               row["eligible_radiogenomics"]=="NOT_ASSESSED",
               "FROZEN_CLINICAL_SOURCE_NOT_ALREADY_APPROVED")
    return {r["patient_id"]:r for r in rows}

def audit(z,orig):
    indexed={k:[] for k in orig}
    files=0
    members=z.infolist()
    for info in members:
        if info.is_dir():continue
        files+=1
        pid=patient(info.filename)
        if pid in indexed:indexed[pid].append(info)
    out=[]
    for pid in sorted(orig):
        found=indexed[pid]
        candidates=[x for x in found if is_dicom_candidate(x.filename) and x.file_size>=132]
        venous=[x for x in candidates if VENOUS.search(x.filename)]
        folders={str(Path(x.filename).parent) for x in candidates}
        status=("SOURCE_DIRECTORY_HAS_DICOM_CANDIDATES_NO_HEADER_QC"
                if candidates else "HOLD_NO_DICOM_LIKE_MEMBER"
                if found else "HOLD_NO_FROZEN_PATIENT_MATCH")
        out.append(dict(
            patient_id=pid,selected_tumor=orig[pid]["representative_tumor_number"],
            original_dicom_archive_patient_members=len(found),
            original_dicom_candidate_members=len(candidates),
            venous_directory_name_hint_members=len(venous),
            distinct_original_source_directories=len(folders),
            source_dicom_example_paths="|".join(x.filename for x in candidates[:3])[:1400],
            source_venous_example_paths="|".join(x.filename for x in venous[:3])[:1400],
            source_directory_status=status,
            StudyUID_from_original_DICOM_header="NOT_ASSESSED",
            SeriesUID_from_original_DICOM_header="NOT_ASSESSED",
            scan_before_HCC_therapy="NOT_ASSESSED",
            RNA_same_index_tumor="NOT_ASSESSED",
            clinical_eligibility="NOT_ASSESSED",biology_tests=0,claim_ceiling="S0"))
    summary=dict(
        stage="HCC_STAGE36_OFFICIAL_ZENODO_ORIGINAL_DICOM_ZIP_SOURCE_DIRECTORY",
        official_zenodo_record="https://zenodo.org/records/8179129",
        original_dicoms_zip_publisher_MD5=ORIGINAL_DECLARED_MD5,
        entire_archive_downloaded=False,entire_archive_MD5_independently_verified=False,
        individual_DICOM_headers_read=False,
        original_zip_directory_entries=len(members),
        original_zip_file_members=files,
        frozen_MRI_patients=14,
        patients_with_source_original_dicom_path=sum(int(x["original_dicom_archive_patient_members"]>0) for x in out),
        patients_with_DICOM_like_original_members=sum(int(x["original_dicom_candidate_members"]>0) for x in out),
        patients_with_PV_naming_hint=sum(int(x["venous_directory_name_hint_members"]>0) for x in out),
        exact_StudyInstanceUID_SeriesInstanceUID_source_header_verified=0,
        original_series_UID_matched_to_selected_NIfTI=0,
        MRI_to_GDC_treatment_episode_chronology_verified=0,
        same_RNA_specimen_to_selected_MRI_lesion_verified=0,
        MRI_RNA_biology_tests=0,clinical_eligible_n="NOT_ASSESSED",
        claim_ceiling="S0",decision="SOURCE_ARCHIVE_DIRECTORY_QC_CLINICAL_MRI_RNA_HOLD")
    return out,summary

def write(path,rows,summary):
    path.mkdir(parents=True,exist_ok=True)
    with (path/"stage36_frozen14_source_dicom_archive_directory.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=COLS);w.writeheader();w.writerows(rows)
    (path/"stage36_original_dicom_archive_inventory_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    lines=["# HCC Stage36 bounded official original DICOM archive source inventory",
      "", "Original Zenodo 8179129 dicoms.zip central-directory only.",
      "Publisher-declared MD5 "+ORIGINAL_DECLARED_MD5+" was NOT verified against whole archive.",
      "Original directory patient path found: "+str(summary["patients_with_source_original_dicom_path"])+"/14.",
      "DICOM-like files found: "+str(summary["patients_with_DICOM_like_original_members"])+"/14.",
      "Venous path hint present: "+str(summary["patients_with_PV_naming_hint"])+"/14.",
      "No original DICOM header or UID verified. No MRI-RNA clinical candidate promoted.",
      "MRI-RNA 0/12 tests, eligibility NOT_ASSESSED, claim S0.","",
      "| Patient | Patient archive entries | DICOM-like candidates | PV filename hints |",
      "|---|---:|---:|---:|"]
    for r in rows:
        lines.append("| "+r["patient_id"]+" | "+
          str(r["original_dicom_archive_patient_members"])+" | "+
          str(r["original_dicom_candidate_members"])+" | "+
          str(r["venous_directory_name_hint_members"])+" |")
    report="\n".join(lines)+"\n"
    (path/"stage36_source_dicom_directory_readme.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE36_ORIGINAL_DICOM_SOURCE_CENTRAL_DIRECTORY_VALID",
          json.dumps(summary,sort_keys=True),flush=True)

def offline():
    ensure(patient("TCGA-BC-A10Y/a/PV/1.dcm")=="TCGA-BC-A10Y","PATIENT_TEST")
    ensure(patient("__MACOSX/TCGA-BC-A10Y/._a.dcm")=="","SIDECAR_TEST")
    ensure(is_dicom_candidate("x/3.1.4.1"),"DICOM_EXTENSIONLESS_TEST")
    ensure(not is_dicom_candidate("x/readme.txt"),"SOURCE_SIDECAR_EXCLUSION_TEST")
    ensure(VENOUS.search("TCGA-BC-A10Y/DATE/pv/1.dcm"),"PV_HINT_TEST")
    ensure(not VENOUS.search("TCGA-BC-A10Y/DATE/art/1.dcm"),"ART_HINT_EXCLUSION_TEST")
    ensure(len(cases())==14,"PATIENT14_TEST")
    print("HCC_STAGE36_FROZEN14_ORIGINAL_DICOM_PATH_OFFLINE_NEGATIVE_FIXTURES_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage36_source_dicom_inventory"))
    a=p.parse_args()
    offline()
    if a.offline_test:return
    with ZipFile(HTTPRangeFile(ARCHIVE)) as z:
        out,summary=audit(z,cases())
    write(a.out_dir,out,summary)
    ensure(summary["patients_with_source_original_dicom_path"]>0,
           "SOURCE_DICOMS_ZIP_NO_ORIGINAL_TCGA_PATIENT_MATCH")
if __name__=="__main__":main()
