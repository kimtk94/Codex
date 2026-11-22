#!/usr/bin/env python3
"""Bounded remote ZIP range extraction of 1 HCC MRI tumor NIfTI per TCGA case.

Verifies ZIP CRC, gzip stream, NIfTI-1 header, nonempty segmentation voxels.
It does NOT establish spatial registration, tumor boundaries, radiologist review
or imaging-before-tissue time. No image data or slices are uploaded as artifacts.
"""
import argparse
import csv
import gc
import gzip
import json
import math
import re
import struct
from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from zenodo_nifti_zip_inventory import ARCHIVE, PATIENT, TUMOR_MASK, is_apple_sidecar, range_bytes

MAX_MEMBER = 16 * 1024 * 1024
MAX_DECOMPRESSED = 192 * 1024 * 1024
DTYPES = {
    2: ("B", 1), 4: ("h", 2), 8: ("i", 4),
    16: ("f", 4), 64: ("d", 8), 256: ("b", 1),
    512: ("H", 2), 768: ("I", 4),
}
CSV_FIELDS = ["patient_id", "nifti_member_path", "member_bytes",
              "nifti_dimensions", "nifti_dtype_code", "mask_nonzero_voxels",
              "mask_total_voxels", "mask_nonzero_fraction", "nifti_spacing",
              "nifti_mask_voxel_status", "image_registration_verified",
              "eligible_mri_rna_patient"]


class HTTPRangeFile:
    def __init__(self, url):
        self.url = url
        tail, total = range_bytes(url, "bytes=-65557", 65557)
        self.total = total
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, pos, whence=0):
        if whence == 0:
            value = pos
        elif whence == 1:
            value = self.pos + pos
        elif whence == 2:
            value = self.total + pos
        else:
            raise ValueError("Unsupported whence")
        if value < 0:
            raise OSError("Negative file offset")
        self.pos = value
        return value

    def read(self, size=-1):
        if self.pos >= self.total:
            return b""
        if size is None or size < 0:
            # ZipFile reads the remainder after seeking close to EOCD.
            # This is safe only when the remaining suffix is within the cap.
            size = self.total - self.pos
        size = min(size, self.total - self.pos)
        if size > MAX_MEMBER:
            raise ValueError("Remote read exceeds per-request safety cap")
        if size == 0:
            return b""
        data, total = range_bytes(
            self.url, f"bytes={self.pos}-{self.pos+size-1}", size)
        if total != self.total or len(data) != size:
            raise RuntimeError("Remote ZIP response did not match requested range")
        self.pos += size
        return data

    def close(self):
        pass


def parse_nifti1_mask(blob):
    import numpy as np
    if len(blob) < 352:
        raise ValueError("NIfTI payload shorter than 352-byte header")
    header = struct.unpack_from("<I", blob, 0)[0]
    if header != 348:
        raise ValueError("NIfTI-1 little-endian header not recognized")
    dims = struct.unpack_from("<8h", blob, 40)
    ndims = dims[0]
    if ndims < 3 or ndims > 4:
        raise ValueError(f"Unexpected mask NIfTI dimensions: {ndims}")
    shape = tuple(dims[1:ndims+1])
    if any(x < 1 or x > 2048 for x in shape):
        raise ValueError(f"Invalid NIfTI shape: {shape}")
    dtype_code = struct.unpack_from("<h", blob, 70)[0]
    if dtype_code not in DTYPES:
        raise ValueError(f"Unsupported segmentation dtype code: {dtype_code}")
    fmt, size = DTYPES[dtype_code]
    bitpix=struct.unpack_from("<h", blob, 72)[0]
    if bitpix != 8*size:
        raise ValueError("Inconsistent NIfTI datatype and bitpix")
    pixdim = struct.unpack_from("<8f", blob, 76)
    spacing = pixdim[1:4]
    if not all(math.isfinite(x) and x > 0 for x in spacing):
        raise ValueError("Invalid voxel spacing")
    offset = struct.unpack_from("<f", blob, 108)[0]
    start = int(round(offset))
    if start < 352:
        raise ValueError("NIfTI vox_offset is not a valid single-file payload offset")
    count = math.prod(shape)
    end = start + count * size
    if end > len(blob):
        raise ValueError(f"Truncated NIfTI voxel payload; expected >= {end} bytes")
    if blob[344:348] != b"n+1\x00":
        raise ValueError("Not a NIfTI-1 single-file image")
    values = np.frombuffer(blob, dtype=np.dtype("<"+{
        "B":"u1","h":"i2","i":"i4","f":"f4","d":"f8","b":"i1","H":"u2","I":"u4"
    }[fmt]), count=count, offset=start)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite values in segmentation mask")
    nz = int(np.count_nonzero(values))
    if nz < 1:
        raise ValueError("Tumor mask has zero nonzero voxels")
    return shape, dtype_code, spacing, nz, count


def load_candidates(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("Missing MRI tumor-mask inventory candidates")
    return {r["patient_id"]:r for r in rows
            if int(r["archive_tumor_mask_files"]) > 0
            and r["tumor_metric_evidence"] == "YES"
            and r["primary_tumor_rna_linked"] == "YES"}


def validate_remote_cases(cases):
    results = []
    remote = HTTPRangeFile(ARCHIVE)
    with ZipFile(remote) as archive:
        available=defaultdict(list)
        for item in archive.infolist():
            if is_apple_sidecar(item.filename) or item.is_dir():
                continue
            if not TUMOR_MASK.search(item.filename.split("/")[-1]):
                continue
            m=PATIENT.search(item.filename)
            if m:
                pid=m.group().upper().replace("_","-")
                if pid in cases:
                    available[pid].append(item)
        for patient in sorted(cases):
            infos = available.get(patient, [])
            if not infos:
                results.append({"patient_id":patient,"nifti_member_path":"",
                                "nifti_mask_voxel_status":"NO_NIFTI_TUMOR_MEMBER"})
                continue
            # Prefer rater1 tumor1 for consistency, then smallest bounded member.
            info = sorted(infos,key=lambda z: (
                0 if re.search(r"rater1_tumor1\.nii",z.filename,re.I) else 1,
                z.file_size,z.filename))[0]
            result={"patient_id":patient,"nifti_member_path":info.filename,
                    "member_bytes":info.file_size}
            try:
                if info.file_size > MAX_MEMBER:
                    raise ValueError(f"Member >16MiB cap: {info.file_size}")
                with archive.open(info) as z:
                    content=z.read(MAX_MEMBER+1)
                if len(content) > MAX_MEMBER:
                    raise ValueError("Member exceeds read limit")
                if info.filename.endswith(".gz"):
                    with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
                        raw=gz.read(MAX_DECOMPRESSED+1)
                else:
                    raw=content
                if len(raw) > MAX_DECOMPRESSED:
                    raise ValueError("NIfTI uncompressed >192MiB cap")
                shape,dtype_code,spacing,nz,count=parse_nifti1_mask(raw)
                result.update({
                    "nifti_dimensions":"x".join(map(str,shape)),
                    "nifti_dtype_code":dtype_code,
                    "mask_nonzero_voxels":nz,
                    "mask_total_voxels":count,
                    "mask_nonzero_fraction":round(nz/count,8),
                    "nifti_spacing":"x".join(f"{x:.5g}" for x in spacing),
                    "nifti_mask_voxel_status":"PASS_NONEMPTY_NIFTI_MASK",
                })
                del raw, content
                gc.collect()
            except Exception as exc:
                result["nifti_mask_voxel_status"] = (
                    f"NOT_VERIFIED_{type(exc).__name__}: {str(exc)[:140]}")
            result["image_registration_verified"]="NO"
            result["eligible_mri_rna_patient"]="NOT_ASSESSED"
            results.append(result)
    return results


def offline_test():
    import numpy as np
    raw=bytearray(352+24)
    struct.pack_into("<I",raw,0,348)
    struct.pack_into("<8h",raw,40,3,2,3,4,1,1,1,1)
    struct.pack_into("<h",raw,70,2)
    struct.pack_into("<h",raw,72,8)
    struct.pack_into("<8f",raw,76,1,1,1,2,1,1,1,1)
    struct.pack_into("<f",raw,108,352)
    raw[344:348]=b"n+1\x00"
    raw[352]=1
    shape,typ,spacing,nz,count=parse_nifti1_mask(bytes(raw))
    assert shape==(2,3,4) and nz==1 and count==24
    assert typ==2 and spacing==(1.,1.,2.)
    assert is_apple_sidecar("__MACOSX/a/._rater1_tumor1.nii.gz")
    print("HCC_MRI_NIFTI_MASK_VOXEL_OFFLINE_TEST_PASS")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="artifacts/hcc_mri")
    parser.add_argument("--offline-test",action="store_true")
    args=parser.parse_args()
    if args.offline_test:
        offline_test()
        return
    root=Path(args.output)
    cases=load_candidates(root/"tcga_liverhccseg_mri_mask_members.csv")
    rows=validate_remote_cases(cases)
    if not rows:
        raise ValueError("Zero MRI tumor-mask files selected")
    path=root/"tcga_liverhccseg_mri_mask_voxel_qc.csv"
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=CSV_FIELDS,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    statuses=Counter(r["nifti_mask_voxel_status"] for r in rows)
    report={
        "status":"PASS_BOUNDED_MASK_VOXEL_QC" if len(statuses)==1 and
                  "PASS_NONEMPTY_NIFTI_MASK" in statuses else "PARTIAL_MASK_QC",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "patient_candidates":len(cases),
        "mask_files_examined":len(rows),
        "nonempty_nifti_mask_patients":statuses["PASS_NONEMPTY_NIFTI_MASK"],
        "status_counts":dict(statuses),
        "image_registration_verified_patients":0,
        "qualified_mri_rna_patients":"NOT_ASSESSED",
        "note":"One public tumor-mask NIfTI file per patient, not full interrater/phase registration validation.",
    }
    (root/"tcga_liverhccseg_mri_mask_voxel_qc_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if report["status"]!="PASS_BOUNDED_MASK_VOXEL_QC":
        raise SystemExit(1)


if __name__=="__main__":
    main()
