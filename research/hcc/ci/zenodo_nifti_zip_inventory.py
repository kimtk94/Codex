#!/usr/bin/env python3
"""Verify LiverHccSeg v1.1 MRI tumor-mask file presence via ZIP central directory.

Reads only the final ZIP directory via bounded HTTP Range requests. Does NOT
download the ~978MB NIfTI archive or validate mask voxels, geometry, or anatomy.
"""
import argparse
import csv
import json
import re
import struct
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO

ARCHIVE = "https://zenodo.org/records/8179129/files/nifti_and_segms.zip?download=1"
PATIENT = re.compile(r"TCGA[-_][A-Z0-9]{2}[-_][A-Z0-9]{4}", re.I)
TUMOR_MASK = re.compile(r"(?:rater|reader)[-_]?\d+[-_]tumou?r[-_]?\d*\.nii(?:\.gz)?$", re.I)
SEG_LIVER = re.compile(r"(?:rater|reader)[-_]?\d+[-_]liver\.nii(?:\.gz)?$", re.I)
PHASE = {"art.nii.gz", "pv.nii.gz", "art_pv.nii.gz", "pre.nii.gz",
         "del.nii.gz", "art_pre.nii.gz", "art_del.nii.gz"}
FIELDS = ["patient_id", "tumor_metric_evidence", "primary_tumor_rna_linked",
          "archive_tumor_mask_files", "archive_liver_mask_files",
          "archive_mri_phase_files", "archive_tumor_mask_member_names",
          "archive_mask_status", "radiogenomics_eligible"]


def range_bytes(url, value, size_limit):
    req=urllib.request.Request(url, headers={
        "Range":value, "Accept-Encoding":"identity",
        "User-Agent":"HCC-public-zip-metadata-audit/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 206:
            raise RuntimeError(f"Archive does not support bounded HTTP ranges (HTTP {r.status})")
        cr=r.headers.get("Content-Range", "")
        if not cr.startswith("bytes ") or "/" not in cr:
            raise ValueError("Cannot determine original ZIP byte offsets")
        total=int(cr.rsplit("/",1)[-1])
        data=r.read(size_limit + 1)
        if len(data) > size_limit:
            raise ValueError("Range response exceeded safety size cap")
    return data,total


def eocd(data):
    pos=data.rfind(b"PK\x05\x06")
    if pos < 0 or pos + 22 > len(data):
        raise ValueError("Standard ZIP EOCD not in final 65557 bytes")
    sig,disk,disk_cd,entries_disk,entries,total_size,cd_offset,comment = struct.unpack_from(
        "<IHHHHIIH", data,pos)
    if disk or disk_cd or entries_disk != entries:
        raise ValueError("Multipart ZIP unsupported")
    if entries == 65535 or total_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise ValueError("ZIP64 layout unsupported by bounded metadata reader")
    if cd_offset + total_size == 0:
        raise ValueError("Missing ZIP entries")
    return entries,total_size,cd_offset


def parse_cd(data, count):
    names=[]
    pos=0
    for _ in range(count):
        if pos+46 > len(data) or data[pos:pos+4]!=b"PK\x01\x02":
            raise ValueError(f"ZIP central directory invalid at offset {pos}")
        n=int.from_bytes(data[pos+28:pos+30],"little")
        x=int.from_bytes(data[pos+30:pos+32],"little")
        c=int.from_bytes(data[pos+32:pos+34],"little")
        end=pos+46+n+x+c
        if end > len(data):
            raise ValueError("Truncated ZIP central-directory entry")
        name=data[pos+46:pos+46+n].decode("utf-8",errors="replace")
        names.append(name)
        pos=end
    return names


def remote_names():
    tail,bytes_total = range_bytes(ARCHIVE,"bytes=-65557",65557)
    entries,cd_size,cd_start=eocd(tail)
    if cd_size>16*1024*1024:
        raise ValueError("ZIP directory >16MiB; use other metadata route")
    if cd_start+cd_size > bytes_total:
        raise ValueError("ZIP offsets outside remote archive")
    directory,total2=range_bytes(
        ARCHIVE,f"bytes={cd_start}-{cd_start+cd_size-1}",16*1024*1024)
    if total2 != bytes_total or len(directory)!=cd_size:
        raise ValueError("ZIP changed or incomplete central directory")
    return parse_cd(directory,entries),bytes_total,cd_size


def is_apple_sidecar(name):
    path = name.replace("\\", "/")
    return "__MACOSX/" in path or path.split("/")[-1].startswith("._")


def filename_patient(name):
    m=PATIENT.search(name)
    return m.group(0).upper().replace("_","-") if m else ""


def summarize(names, mri_rows):
    by=defaultdict(list)
    for f in names:
        if is_apple_sidecar(f):
            continue
        pid=filename_patient(f)
        if pid:
            by[pid].append(f)
    results=[]
    for row in mri_rows:
        pid=row["patient_id"]
        members=by.get(pid,[])
        tumor=sorted(f for f in members if TUMOR_MASK.search(f.split("/")[-1]))
        liver=sorted(f for f in members if SEG_LIVER.search(f.split("/")[-1]))
        phases=sorted(f for f in members if f.split("/")[-1].lower() in PHASE)
        results.append({
            "patient_id":pid,
            "tumor_metric_evidence":row["hcc_tumor_annotation_metrics_present"],
            "primary_tumor_rna_linked":row["mri_rna_case_barcode_overlap"],
            "archive_tumor_mask_files":len(tumor),
            "archive_liver_mask_files":len(liver),
            "archive_mri_phase_files":len(phases),
            "archive_tumor_mask_member_names":"|".join(tumor),
            "archive_mask_status":(
                "MEMBER_PRESENT_VOXELS_NOT_VALIDATED" if tumor else "NO_TUMOR_MASK_MEMBER_DETECTED"),
            "radiogenomics_eligible":"NOT_ASSESSED",
        })
    metrics={r["patient_id"] for r in mri_rows
             if r["hcc_tumor_annotation_metrics_present"]=="YES"}
    present={r["patient_id"] for r in results if r["archive_tumor_mask_files"]>0}
    summary={
        "status":"PASS_ZIP_DIRECTORY_METADATA_ONLY",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "total_archive_member_names":len(names),
        "excluded_appledouble_sidecars":sum(is_apple_sidecar(n) for n in names),
        "archive_members_with_patient_barcodes":sum(bool(filename_patient(x)) for x in names),
        "mri_metadata_patients":len(mri_rows),
        "tumor_metric_patients":len(metrics),
        "patients_with_tumor_mask_archive_member":len(present),
        "tumor_metric_and_mask_member_intersection":len(metrics&present),
        "tumor_metric_without_mask_member":len(metrics-present),
        "tumor_mask_member_without_metric":len(present-metrics),
        "rna_linked_tumor_mask_member_patients":sum(
            r["archive_tumor_mask_files"]>0 and r["primary_tumor_rna_linked"]=="YES"
            for r in results),
        "verified_mri_roi_rna_pairs":"NOT_ASSESSED",
        "note":"Remote ZIP file names only, not voxel content, ROI correctness, scan alignment or pretreatment timing."
    }
    return results,summary


def offline_test():
    import zipfile
    data=BytesIO()
    with zipfile.ZipFile(data,"w",compression=zipfile.ZIP_STORED) as z:
        z.writestr("TCGA-AA-0001/rater1_tumor1.nii.gz",b"small dummy")
        z.writestr("TCGA-AA-0001/art.nii.gz",b"small dummy")
        z.writestr("__MACOSX/TCGA-AA-0001/._rater3_tumor1.nii.gz",b"fake")
    raw=data.getvalue()
    n,l,offset=eocd(raw[-65557:])
    names=parse_cd(raw[offset:offset+l],n)
    r,s=summarize(names,[{
        "patient_id":"TCGA-AA-0001",
        "hcc_tumor_annotation_metrics_present":"YES",
        "mri_rna_case_barcode_overlap":"YES"}])
    assert s["patients_with_tumor_mask_archive_member"]==1
    assert s["excluded_appledouble_sidecars"]==1
    assert r[0]["archive_tumor_mask_files"]==1
    assert s["rna_linked_tumor_mask_member_patients"]==1
    assert r[0]["radiogenomics_eligible"]=="NOT_ASSESSED"
    print("HCC_ZENODO_MRI_MASK_ZIP_DIRECTORY_OFFLINE_TEST_PASS")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="artifacts/hcc_mri")
    parser.add_argument("--offline-test",action="store_true")
    args=parser.parse_args()
    if args.offline_test:
        offline_test()
        return
    root=Path(args.output)
    with (root/"tcga_liverhccseg_mri_rna_candidates.csv").open(
            encoding="utf-8",newline="") as f:
        reader=csv.DictReader(f)
        mri_rows=list(reader)
    if not mri_rows:
        raise ValueError("Missing MRI/TCGA metadata cohort candidates")
    try:
        names,total_bytes,cd_size=remote_names()
        results,report=summarize(names,mri_rows)
        report["remote_zip_total_bytes"]=total_bytes
        report["central_directory_bytes_downloaded"]=cd_size
        with (root/"tcga_liverhccseg_mri_mask_members.csv").open(
                "w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(results)
        # Only public archive filenames; no image contents.
    except Exception as exc:
        report={"status":"ZIP_DIRECTORY_NOT_VERIFIED","error_class":type(exc).__name__,
                "error":str(exc)[:500], "verified_mri_roi_rna_pairs":"NOT_ASSESSED"}
    (root/"tcga_liverhccseg_nifti_zip_inventory_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if report["status"]=="ZIP_DIRECTORY_NOT_VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
