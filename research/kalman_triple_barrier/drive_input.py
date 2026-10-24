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
    encoded=os.environ.get('GDRIVE_SA_JSON_B64')
    if not encoded:raise SystemExit('BLOCKED: GDRIVE_SA_JSON_B64 secret missing; no public-data fallback')
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    creds=service_account.Credentials.from_service_account_info(json.loads(base64.b64decode(encoded)),scopes=['https://www.googleapis.com/auth/drive.readonly'])
    api=build('drive','v3',credentials=creds,cache_discovery=False)
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
