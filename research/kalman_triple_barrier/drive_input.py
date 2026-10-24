"""Read-only import of selected private Google Drive historical parquet files.
Requires explicit CI credential. Never commits raw data to Git.
"""
import argparse,base64,io,json,os
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--file-id',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    raw=os.environ.get('CKD_DRIVE_SA_JSON','').strip()
    encoded=os.environ.get('GDRIVE_SA_JSON_B64','').strip()
    if not raw and not encoded:raise SystemExit('BLOCKED: no configured Drive credential (CKD_DRIVE_SA_JSON / GDRIVE_SA_JSON_B64)')
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    creds=service_account.Credentials.from_service_account_info(json.loads(raw) if raw else json.loads(base64.b64decode(encoded)),scopes=['https://www.googleapis.com/auth/drive.readonly'])
    api=build('drive','v3',credentials=creds,cache_discovery=False)
    # Check Drive ACL without disclosing service-account email or metadata.
    from googleapiclient.errors import HttpError
    try:
        api.files().get(fileId=a.file_id,fields='id,mimeType',supportsAllDrives=True).execute()
    except HttpError as exc:
        status=getattr(exc.resp,'status',0)
        if status in (403,404):
            raise SystemExit('BLOCKED: private Drive file unavailable to CI service account; grant service-account Viewer access to this file (or a parent folder)') from None
        raise
    req=api.files().get_media(fileId=a.file_id)
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix('.part')
    try:
        with tmp.open('wb') as stream:
            dl=MediaIoBaseDownload(stream,req)
            done=False
            while not done:_,done=dl.next_chunk()
        tmp.rename(output)
        print('PRIVATE_SOURCE_IMPORTED bytes=',output.stat().st_size)
    finally:
        tmp.unlink(missing_ok=True)
if __name__=='__main__':main()
