#!/usr/bin/env python3
"""One-time, explicitly dispatched archival of unapproved research candidates.

Only a separately owner-provisioned file seeded with the verified original ZIP
is eligible. The canonical source is never a write target. No public artifact
contains price bytes; no research release is implied by storage.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re

from candidate_compare import KEYS, open_verified
from refresh_ci import json_write, parse_google_credentials

ORIGINAL_ID = "1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd"
ORIGINAL_SHA256 = "d524bc234e66632e9f1f052ecebff7df4cbd1e6d1afbfc8e1b4d92c6f7a7d829"
CANDIDATE_FOLDER_ID = "1Fwkq_Ntzhv8IVyd5oygj1-oEDtQHG8ea"
MAX_BYTES = 50 * 1024 * 1024
HEX64 = re.compile(r"[a-f0-9]{64}")
FILE_ID = re.compile(r"[A-Za-z0-9_-]{15,100}")
RUN_ID = re.compile(r"[1-9][0-9]{5,20}")


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def validate_target(meta, target_id, expected_session):
    if (not FILE_ID.fullmatch(target_id) or target_id == ORIGINAL_ID
            or meta.get("id") != target_id
            or meta.get("parents") != [CANDIDATE_FOLDER_ID]
            or meta.get("name") != f"UNFILLED_market_candidate_{expected_session}.zip"
            or meta.get("mimeType") != "application/zip"
            or meta.get("trashed") is not False
            or meta.get("capabilities", {}).get("canEdit") is not True):
        raise ValueError("UNAPPROVED_OR_CONSUMED_CANDIDATE_SLOT")
    permissions = meta.get("permissions")
    if (not isinstance(permissions, list) or len(permissions) != 2
            or sorted(p.get("role", "") for p in permissions) != ["owner", "writer"]
            or any(p.get("type") != "user" for p in permissions)):
        raise ValueError("CANDIDATE_SLOT_NOT_FILE_SCOPED")


def validate_candidate(original, candidate, audit, expected_session):
    if date.fromisoformat(expected_session).isoformat() != expected_session:
        raise ValueError("INVALID_EXPECTED_SESSION")
    if not 0 < len(candidate) <= MAX_BYTES:
        raise ValueError("CANDIDATE_SIZE_INVALID")
    if digest(original) != ORIGINAL_SHA256 or digest(candidate) == digest(original):
        raise ValueError("ORIGINAL_CHANGED_OR_CANDIDATE_EQUALS_SEED")
    z, manifest, ready = open_verified(candidate)
    with z:
        if (ready.get("expected_last_completed_nyse_session") != expected_session
                or manifest.get("fred_series_success") != 12):
            raise ValueError("CANDIDATE_SESSION_OR_FRED_MISMATCH")
    if (audit.get("schema") != "kalman-market-overlap-audit-v2"
            or audit.get("status") != "CANDIDATE_COMPARISON_RESEARCH_HOLD"
            or audit.get("original_sha256") != digest(original)
            or audit.get("candidate_sha256") != digest(candidate)
            or audit.get("candidate_asof") != expected_session
            or audit.get("assets_compared") != len(KEYS)
            or audit.get("approved_assets_for_merge") != 0
            or audit.get("approved_rows_for_merge") != 0
            or audit.get("ready_for_pit_training") is not False
            or audit.get("production_writes") is not False
            or audit.get("original_drive_zip_replaced") is not False):
        raise ValueError("MISSING_OR_UNSAFE_CANDIDATE_AUDIT")
    rows = audit.get("assets")
    if (not isinstance(rows, list) or len(rows) != len(KEYS)
            or {r.get("key") for r in rows} != set(KEYS)
            or any(r.get("release") != "HOLD" for r in rows)):
        raise ValueError("INCOMPLETE_CANDIDATE_ASSET_AUDIT")


def save_once(client, *, original, candidate, audit, target_id, expected_session, run_id):
    """Client is injected for tests; one permitted write plus byte-level readback."""
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("INVALID_RUN_ID")
    validate_candidate(original, candidate, audit, expected_session)
    # Reject canonical and malformed ids before even reading target metadata.
    if not FILE_ID.fullmatch(target_id) or target_id == ORIGINAL_ID:
        raise ValueError("UNAPPROVED_CANDIDATE_TARGET")
    meta = client.metadata(target_id)
    validate_target(meta, target_id, expected_session)
    if digest(client.download(target_id)) != ORIGINAL_SHA256:
        raise ValueError("CANDIDATE_SLOT_SEED_CHANGED_OR_CONSUMED")
    # Serial workflow, fresh metadata check just before write. No retries of
    # an already consumed slot; interrupted writes need owner review.
    validate_target(client.metadata(target_id), target_id, expected_session)
    client.write_bytes(target_id, candidate)
    if digest(client.download(target_id)) != digest(candidate):
        raise RuntimeError("CANDIDATE_REMOTE_SHA256_MISMATCH")
    final_name = f"market_candidate_HOLD_{expected_session}_GH{run_id}.zip"
    client.rename(target_id, final_name)
    final = client.metadata(target_id)
    if (final.get("id") != target_id or final.get("name") != final_name
            or final.get("parents") != [CANDIDATE_FOLDER_ID]
            or final.get("trashed") is not False
            or digest(client.download(target_id)) != digest(candidate)):
        raise RuntimeError("CANDIDATE_FINAL_READBACK_MISMATCH")
    return {
        "schema": "kalman-private-candidate-archive-v1",
        "status": "PRIVATE_CANDIDATE_STORED_RESEARCH_HOLD",
        "filename": final_name,
        "candidate_sha256": digest(candidate),
        "candidate_bytes": len(candidate),
        "candidate_asof": expected_session,
        "original_sha256": digest(original),
        "original_drive_zip_replaced": False,
        "private_candidate_archive_persisted": True,
        "remote_sha256_verified": True,
        "approved_rows_for_merge": 0,
        "ready_for_pit_training": False,
        "production_writes": False,
    }


class DriveClient:
    def __init__(self):
        from googleapiclient.discovery import build
        self.service = build("drive", "v3", credentials=parse_google_credentials(),
                             cache_discovery=False)

    def metadata(self, file_id):
        return self.service.files().get(
            fileId=file_id, supportsAllDrives=True,
            fields="id,name,mimeType,parents,trashed,capabilities(canEdit),permissions(type,role)"
        ).execute()

    def download(self, file_id):
        from googleapiclient.http import MediaIoBaseDownload
        out = io.BytesIO()
        reader = MediaIoBaseDownload(out, self.service.files().get_media(
            fileId=file_id, supportsAllDrives=True), chunksize=2 * 1024 * 1024)
        done = False
        while not done:
            _, done = reader.next_chunk(num_retries=0)
            if out.tell() > MAX_BYTES:
                raise RuntimeError("REMOTE_ARCHIVE_SIZE_LIMIT")
        return out.getvalue()

    def write_bytes(self, file_id, data):
        from googleapiclient.http import MediaIoBaseUpload
        self.service.files().update(
            fileId=file_id, supportsAllDrives=True,
            media_body=MediaIoBaseUpload(io.BytesIO(data), mimetype="application/zip",
                                         resumable=True), fields="id"
        ).execute(num_retries=0)

    def rename(self, file_id, name):
        self.service.files().update(fileId=file_id, supportsAllDrives=True,
                                    body={"name": name}, fields="id").execute(num_retries=0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--original", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--audit", required=True)
    p.add_argument("--target-id", required=True)
    p.add_argument("--expected-session", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    original, candidate = Path(a.original).read_bytes(), Path(a.candidate).read_bytes()
    audit = json.loads(Path(a.audit).read_text())
    # Validate offline before accessing the service or its credentials.
    validate_candidate(original, candidate, audit, a.expected_session)
    report = save_once(DriveClient(), original=original, candidate=candidate, audit=audit,
                       target_id=a.target_id, expected_session=a.expected_session, run_id=a.run_id)
    json_write(a.out, report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
