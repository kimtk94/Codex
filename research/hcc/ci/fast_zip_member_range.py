#!/usr/bin/env python3
"""Fetch one public ZIP archive member with two bounded HTTP ranges.

The source Zenodo ZIP central directory was verified by the existing inventory
audit. This eliminates hundreds of per-MiB range calls when extracting NIfTIs,
mitigating intermittent Zenodo HTTP 429. CRC and expected member sizes enforced.
Only supports ZIP stored (0) or deflated (8), non-encrypted entries.
"""
import binascii
import struct
import zlib
from zenodo_nifti_zip_inventory import range_bytes

MAX_MEMBER_IN_ZIP = 96 * 1024 * 1024


def get_member_with_ranges(url, info, total_bytes, fetch=range_bytes):
    """ZipInfo metadata comes from a previously parsed trusted ZIP directory."""
    if info.flag_bits & 1:
        raise ValueError("Encrypted ZIP member unsupported")
    if info.compress_type not in (0, 8):
        raise ValueError("Unsupported ZIP compression method")
    if info.file_size > MAX_MEMBER_IN_ZIP or info.compress_size > MAX_MEMBER_IN_ZIP:
        raise ValueError("ZIP member above 96MiB network cap")
    offset = info.header_offset
    header, total = fetch(url, f"bytes={offset}-{offset+29}", 30)
    if total != total_bytes or len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise ValueError("Invalid ZIP local member header")
    name_length, extra_length = struct.unpack_from("<HH", header, 26)
    start = offset + 30 + name_length + extra_length
    if start + info.compress_size > total_bytes:
        raise ValueError("ZIP member outside declared archive size")
    if info.compress_size == 0:
        if info.file_size:
            raise ValueError("Missing ZIP compressed bytes")
        content = b""
    else:
        compressed, total_again = fetch(
            url, f"bytes={start}-{start+info.compress_size-1}", info.compress_size)
        if total_again != total_bytes or len(compressed) != info.compress_size:
            raise RuntimeError("Partial or mutated remote ZIP compressed member")
        if info.compress_type == 0:
            content = compressed
        else:
            dec = zlib.decompressobj(-zlib.MAX_WBITS)
            content = dec.decompress(compressed, MAX_MEMBER_IN_ZIP + 1)
            if dec.unconsumed_tail or not dec.eof or dec.unused_data:
                raise ValueError("Truncated/oversized ZIP deflate stream")
    if len(content) != info.file_size:
        raise ValueError("Uncompressed ZIP member size mismatch")
    crc = binascii.crc32(content) & 0xffffffff
    if crc != info.CRC:
        raise ValueError("CRC mismatch")
    return content


def offline_test():
    import io
    from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
    for method in (ZIP_STORED, ZIP_DEFLATED):
        out = io.BytesIO()
        with ZipFile(out, "w", compression=method) as archive:
            archive.writestr("TCGA-AA-0001/pv.nii.gz", b"Hello HCC" * 1000)
        blob = out.getvalue()
        with ZipFile(io.BytesIO(blob)) as archive:
            info = archive.getinfo("TCGA-AA-0001/pv.nii.gz")
        calls = []
        def fixture(url, selector, cap):
            assert selector.startswith("bytes=")
            a, b = map(int, selector.split("=")[1].split("-"))
            calls.append(selector)
            assert b-a+1 <= cap
            return blob[a:b+1],len(blob)
        got = get_member_with_ranges("https://example.invalid/archive", info,
                                     len(blob), fetch=fixture)
        assert got == b"Hello HCC" * 1000 and len(calls) == 2
    print("HCC_FAST_ZIP_MEMBER_RANGE_OFFLINE_TEST_PASS")


if __name__ == "__main__":
    offline_test()
