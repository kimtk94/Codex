#!/usr/bin/env python3
"""Fetch exactly the private research ZIP from Drive. Read only; no credentials logged."""
import argparse
import io
import os
from pathlib import Path
import sys


APPROVED_READONLY_ARCHIVES = {
    '1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd': (
        'kalman_market_research_latest.zip', 35 * 1024 * 1024),
    '1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE': (
        'daily20_data_latest.zip', 50 * 1024 * 1024),
}


def download(file_id, out):
    if file_id not in APPROVED_READONLY_ARCHIVES:
        raise ValueError('UNAPPROVED_DRIVE_FILE')
    expected_name, size_cap = APPROVED_READONLY_ARCHIVES[file_id]
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from research.kalman_market_refresh.refresh_ci import parse_google_credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    service=build('drive','v3',credentials=parse_google_credentials(),cache_discovery=False)
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
    import hashlib
    blob=buf.getvalue()
    if len(blob) != int(meta['size']) or (
        meta.get('md5Checksum') and
        hashlib.md5(blob).hexdigest() != meta['md5Checksum']
    ):
        raise RuntimeError('REMOTE_DRIVE_BYTES_NOT_MATCHING_METADATA')
    out.write_bytes(blob)
    print('READ_ONLY_DRIVE_DOWNLOAD_OK bytes='+str(out.stat().st_size),
          'file='+expected_name, 'sha256='+hashlib.sha256(blob).hexdigest())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--file-id',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();download(a.file_id,a.out)