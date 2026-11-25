#!/usr/bin/env python3
"""Fetch exactly the private research ZIP from Drive. Read only; no credentials logged."""
import argparse
import io
import hashlib
import os
from pathlib import Path
import sys


PINNED_CANDIDATE_ID = '1rptk7B9dJfNp2GgaDF0g27FZUolKEIDn'
PINNED_CANDIDATE_SHA256 = '62b08e06a84caef53889f17bf75afde5bb2d2cd01e9adc5c6433b9c2e7c89722'
PINNED_CANDIDATE_BYTES = 2151240

APPROVED_READONLY_ARCHIVES = {
    PINNED_CANDIDATE_ID: ('market_candidate_HOLD_2026-11-24_GH45533778910.zip', PINNED_CANDIDATE_BYTES),
    '1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd': (
        'kalman_market_research_latest.zip', 35 * 1024 * 1024),
    '1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE': (
        'daily20_data_latest.zip', 50 * 1024 * 1024),
}


def verify_pinned_candidate(file_id, blob):
    """The consumed HOLD slot is an immutable input, not a new write target."""
    if file_id == PINNED_CANDIDATE_ID and (
        len(blob) != PINNED_CANDIDATE_BYTES or hashlib.sha256(blob).hexdigest() != PINNED_CANDIDATE_SHA256
    ):
        raise RuntimeError('PINNED_CANDIDATE_BYTES_MISMATCH')


def download(file_id, out):
    if file_id not in APPROVED_READONLY_ARCHIVES:
        raise ValueError('UNAPPROVED_DRIVE_FILE')
    expected_name, size_cap = APPROVED_READONLY_ARCHIVES[file_id]
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from research.kalman_market_refresh.refresh_ci import parse_google_credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    credentials=parse_google_credentials().with_scopes(['https://www.googleapis.com/auth/drive.readonly'])
    service=build('drive','v3',credentials=credentials,cache_discovery=False)
    meta=service.files().get(fileId=file_id,fields='id,name,mimeType,size,md5Checksum',supportsAllDrives=True).execute()
    if meta.get('id') != file_id or meta.get('name') != expected_name or meta.get('mimeType')!='application/zip':
        raise RuntimeError('UNEXPECTED_SOURCE_FILE')
    if not 0 < int(meta.get('size') or 0) <= size_cap:
        raise RuntimeError('OVER_SIZE_LIMIT')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    buf=io.BytesIO()
    downloader=MediaIoBaseDownload(buf,service.files().get_media(fileId=file_id,supportsAllDrives=True),chunksize=2*1024*1024)
    done=False
    while not done:
        _,done=downloader.next_chunk()
        if buf.tell()>size_cap:
            raise RuntimeError('OVER_SIZE_LIMIT')
    blob=buf.getvalue()
    if len(blob) != int(meta['size']) or (
        meta.get('md5Checksum') and
        hashlib.md5(blob).hexdigest() != meta['md5Checksum']
    ):
        raise RuntimeError('REMOTE_DRIVE_BYTES_NOT_MATCHING_METADATA')
    verify_pinned_candidate(file_id,blob)
    out.write_bytes(blob)
    print('READ_ONLY_DRIVE_DOWNLOAD_OK bytes='+str(out.stat().st_size),
          'file='+expected_name, 'sha256='+hashlib.sha256(blob).hexdigest())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--file-id',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();download(a.file_id,a.out)