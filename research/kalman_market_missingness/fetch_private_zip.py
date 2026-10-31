#!/usr/bin/env python3
"""Fetch exactly the private research ZIP from Drive. Read only; no credentials logged."""
import argparse
import io
import os
from pathlib import Path
import sys


def download(file_id, out):
    if file_id != '1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd':
        raise ValueError('UNAPPROVED_DRIVE_FILE')
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from research.kalman_market_refresh.refresh_ci import parse_google_credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    service=build('drive','v3',credentials=parse_google_credentials(),cache_discovery=False)
    meta=service.files().get(fileId=file_id,fields='id,name,mimeType,size',supportsAllDrives=True).execute()
    if meta.get('name')!='kalman_market_research_latest.zip' or meta.get('mimeType')!='application/zip':
        raise RuntimeError('UNEXPECTED_SOURCE_FILE')
    if int(meta.get('size') or 0)>35*1024*1024:
        raise RuntimeError('OVER_SIZE_LIMIT')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    buf=io.BytesIO()
    downloader=MediaIoBaseDownload(buf,service.files().get_media(fileId=file_id,supportsAllDrives=True),chunksize=2*1024*1024)
    done=False
    while not done:
        _,done=downloader.next_chunk()
    out.write_bytes(buf.getvalue())
    print('READ_ONLY_DRIVE_DOWNLOAD_OK bytes='+str(out.stat().st_size))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--file-id',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();download(a.file_id,a.out)