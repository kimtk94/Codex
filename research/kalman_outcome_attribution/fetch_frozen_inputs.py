"""Read the two exact versioned inputs using Drive read-only OAuth scope."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from outcome_profile import ARCHIVES, load_archive


def download(kind, root):
    file_id, expected_name, _, expected_size, _ = ARCHIVES[kind]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from research.kalman_market_refresh.refresh_ci import parse_google_credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    credentials = parse_google_credentials().with_scopes(
        ["https://www.googleapis.com/auth/drive.readonly"])
    client = build("drive","v3",credentials=credentials,cache_discovery=False)
    meta = client.files().get(fileId=file_id,supportsAllDrives=True,
                              fields="id,name,mimeType,size,trashed").execute()
    if (meta.get("id") != file_id or meta.get("name") != expected_name
            or meta.get("mimeType") != "application/zip" or meta.get("trashed") is not False
            or int(meta.get("size") or 0) != expected_size):
        raise ValueError("PINNED_INPUT_IDENTITY_MISMATCH")
    target = Path(root)/f"{kind}.zip"
    with target.open("wb") as out:
        loader = MediaIoBaseDownload(out,client.files().get_media(
            fileId=file_id,supportsAllDrives=True),chunksize=1024*1024)
        done = False
        while not done:
            _,done = loader.next_chunk(num_retries=0)
            if out.tell()>expected_size:
                raise ValueError("PINNED_INPUT_SIZE_LIMIT")
    load_archive(target,kind)
    print("VERIFIED_FROZEN_INPUT",kind,expected_size)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    a=p.parse_args()
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    for kind in ARCHIVES:
        download(kind,root)
