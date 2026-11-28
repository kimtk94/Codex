"""Pinned Drive backup reader; no Drive write, source mutation or trading."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from cache_rehearsal import PRIOR_PIN, PINS
from evidence_review import VERIFIED
from independent_review import independent_review

FILE_ID = "1beheJeFH9biKkeyK8rC574bIiuNRM_Vd"
FILE_NAME = "daily20_issuer_evidence_prior_run46014825695_sha956a7a17.zip"
FILE_SIZE = 14733678
ACCOUNT = "ckd-research-automation@novogene-css-automation.iam.gserviceaccount.com"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"

def validate_identity(env):
    raw = env.get("CKD_DRIVE_SA_JSON", "").strip()
    if not raw:
        encoded = env.get("GDRIVE_SA_JSON_B64", "").strip()
        if encoded:
            raw = base64.b64decode(encoded, validate=True).decode("utf-8")
    if not raw:
        raise ValueError("DRIVE_CREDENTIAL_MISSING")
    data = json.loads(raw)
    if data.get("type") != "service_account" or data.get("client_email") != ACCOUNT:
        raise ValueError("DRIVE_IDENTITY_MISMATCH")
    return data

def validate_metadata(meta):
    if (meta.get("id") != FILE_ID or meta.get("name") != FILE_NAME
            or meta.get("mimeType") != "application/zip"
            or str(meta.get("size")) != str(FILE_SIZE)
            or meta.get("trashed") is not False):
        raise ValueError("DRIVE_TARGET_METADATA_MISMATCH")

class BoundedBuffer(io.BytesIO):
    def write(self, value):
        if self.tell() + len(value) > FILE_SIZE:
            raise ValueError("DRIVE_DOWNLOAD_OVERSIZE")
        return super().write(value)

def verify_blob(blob):
    if len(blob) != FILE_SIZE or hashlib.sha256(blob).hexdigest() != PRIOR_PIN:
        raise ValueError("DRIVE_BACKUP_PIN_MISMATCH")
    return blob

def download(service, downloader_type):
    files = service.files()
    meta = files.get(fileId=FILE_ID, fields="id,name,mimeType,size,trashed",
                     supportsAllDrives=True).execute()
    validate_metadata(meta)
    stream = BoundedBuffer()
    req = files.get_media(fileId=FILE_ID, supportsAllDrives=True)
    downloader = downloader_type(stream, req, chunksize=1024*1024)
    done = False
    for _ in range(32):
        _, done = downloader.next_chunk(num_retries=2)
        if done:
            break
    if not done:
        raise ValueError("DRIVE_DOWNLOAD_INCOMPLETE")
    return verify_blob(stream.getvalue())

def review_blob(blob):
    verify_blob(blob)
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "pinned.zip"
        path.write_bytes(blob)
        report = independent_review(path, PRIOR_PIN)
    for sid, pin in PINS.items():
        entry = report["sources"][sid]
        if (entry.get("state") != VERIFIED or entry.get("sha256") != pin
                or entry.get("independent_anchors_verified") is not True):
            raise ValueError("DRIVE_SOURCE_REVIEW_HOLD:" + sid)
    return {"status": "DRIVE_PINNED_READBACK_VERIFIED",
            "archive_sha256": PRIOR_PIN, "bytes": len(blob),
            "verified_source_count": len(PINS), "research_only": True,
            "remote_write": False, "production_writes": False,
            "cache_reuse_authorized": False, "issuer_payments_certified": 0,
            "source_finality_verified": 0, "strategy_promoted": False}

def main():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    credentials = service_account.Credentials.from_service_account_info(
        validate_identity(os.environ), scopes=[SCOPE])
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    print(json.dumps(review_blob(download(service, MediaIoBaseDownload)), sort_keys=True))

if __name__ == "__main__":
    main()
