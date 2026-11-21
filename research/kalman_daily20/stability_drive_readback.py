#!/usr/bin/env python3
"""Independent read-only Drive result ZIP readback after Daily20 publishing.

Verifies the bytes actually stored at the pinned Google Drive file ID against
the locally constructed results ZIP and every snapshot's archived SHA256.
Never writes to Google Drive, a broker, or a production model.
"""
from __future__ import annotations

import argparse
from hashlib import md5, sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

# Reuse the exact uploader pin. Never maintain a second mutable copy.
from publish_drive import EXPECTED_TARGETS

EXPECTED_DRIVE_RESULTS_ID, EXPECTED_DRIVE_RESULTS_NAME = EXPECTED_TARGETS["results"]
EXPECTED_STABILITY_VERSION = "daily20-prospective-stability-v1"
MAX_RESULTS_SIZE = 50_000_000
SNAPSHOT_PREFIX = "research/stability/snapshots/"


def checksum(blob):
    return sha256(blob).hexdigest()


def verify_results_blob(blob, *, require_stability=True):
    if not blob or len(blob) > MAX_RESULTS_SIZE:
        raise RuntimeError("READBACK_RESULT_ZIP_MISSING_OR_TOO_LARGE")
    with ZipFile(BytesIO(blob)) as z:
        names = z.namelist()
        if (len(set(names)) != len(names) or
            any(name.startswith("/") or "\\" in name or
                ".." in Path(name).parts for name in names)):
            raise RuntimeError("READBACK_UNSAFE_ZIP_NAMES")
        if "drive_manifest.json" not in names:
            raise RuntimeError("READBACK_MANIFEST_MISSING")
        manifest = json.loads(z.read("drive_manifest.json"))
        if (manifest.get("format") != "kalman-daily20-drive-v1"
                or manifest.get("research_only") is not True
                or manifest.get("production_writes") is not False
                or manifest.get("oos_score_count") != 20):
            raise RuntimeError("READBACK_INVALID_RESULTS_MANIFEST")
        signatures = manifest.get("payload_hashes_sha256")
        if not isinstance(signatures, dict) or set(signatures) != set(names) - {
                "drive_manifest.json"}:
            raise RuntimeError("READBACK_INCOMPLETE_MEMBER_MANIFEST")
        for name, expected in signatures.items():
            if checksum(z.read(name)) != expected:
                raise RuntimeError("READBACK_MEMBER_SHA256_MISMATCH:" + name)
        stability_file = "research/stability/report.json"
        if stability_file not in names:
            if require_stability:
                raise RuntimeError("READBACK_STABILITY_REPORT_MISSING")
            return {
                "session": manifest.get("data_expected_last_closed_xnys"),
                "snapshot_count": 0, "research_hold": None,
                "status": "LEGACY_NO_STABILITY_REPORT",
            }
        report = json.loads(z.read(stability_file))
        asof = str(manifest.get("data_expected_last_closed_xnys"))
        if (report.get("version") != EXPECTED_STABILITY_VERSION
                or report.get("session") != asof
                or report.get("research_only") is not True
                or report.get("production_writes") is not False
                or report.get("promotional_attribution_allowed") is not False
                or report.get("strategy_promoted") is not False
                or type(report.get("research_hold")) is not bool
                or manifest.get("stability_status") != report.get("status")
                or manifest.get("stability_research_hold") != report.get("research_hold")):
            raise RuntimeError("READBACK_STABILITY_GOVERNANCE_INVALID")
        finality_digest = report.get("source_finality_evidence_sha256")
        if finality_digest is not None:
            path = "research/source_finality/report.json"
            if path not in names or checksum(z.read(path)) != finality_digest:
                raise RuntimeError("READBACK_SOURCE_FINALITY_EVIDENCE_HASH_MISMATCH")
            finality = json.loads(z.read(path))
            if (finality.get("version") != "daily20-source-finality-v1"
                    or finality.get("session") != asof
                    or finality.get("required") != 26
                    or finality.get("examined") != 26
                    or finality.get("verified") != 0
                    or finality.get("research_hold") is not True
                    or finality.get("strategy_promoted") is not False
                    or finality.get("status") != report.get("source_finality_status")
                    or manifest.get("source_finality_status") != finality["status"]
                    or manifest.get("source_finality_verified_assets") != 0
                    or manifest.get("source_finality_evidence_sha256") != finality_digest
                    or report.get("source_finality_research_hold") is not True
                    or report.get("research_hold") is not True
                    or report.get("status") not in (
                        "SOURCE_FINALITY_HOLD", "REPLAY_DRIFT_RESEARCH_HOLD")):
                raise RuntimeError("READBACK_UNVERIFIED_SOURCE_FINALITY_NOT_HELD")
        frozen_names = sorted(name for name in names
                              if name.startswith(SNAPSHOT_PREFIX)
                              and name.endswith(".json"))
        if len(frozen_names) != report.get("frozen_sessions_preserved"):
            raise RuntimeError("READBACK_FROZEN_SNAPSHOT_COUNT_MISMATCH")
        frozen_hashes = {}
        for name in frozen_names:
            raw = z.read(name)
            item = json.loads(raw)
            day = name[len(SNAPSHOT_PREFIX):-5]
            if (item.get("schema") != EXPECTED_STABILITY_VERSION
                    or item.get("session") != day
                    or item.get("research_only") is not True
                    or item.get("production_writes") is not False):
                raise RuntimeError("READBACK_FROZEN_SNAPSHOT_SCHEMA_INVALID:" + name)
            frozen_hashes[day] = checksum(raw)
        current_hash = frozen_hashes.get(asof)
        if report.get("current_session_has_original_snapshot") is True:
            if not current_hash or current_hash != report.get("frozen_snapshot_sha256"):
                raise RuntimeError("READBACK_FROZEN_CURRENT_HASH_INVALID")
            if finality_digest and report.get("new_sealed_bull_signals") == 20:
                captured = json.loads(z.read(SNAPSHOT_PREFIX + asof + ".json"))
                captured_gate = captured.get("source_finality_at_capture", {})
                if (captured_gate.get("evidence_sha256") != finality_digest
                        or captured_gate.get("provisional") is not True
                        or captured_gate.get("verified") != 0
                        or captured_gate.get("research_hold") is not True):
                    raise RuntimeError("READBACK_FALSE_FIRST_SEAL_FINALITY_APPROVAL")
        elif report.get("frozen_snapshot_sha256") is not None:
            raise RuntimeError("READBACK_FALSE_LEGACY_FROZEN_HASH")
        return {
            "session": asof, "snapshot_count": len(frozen_names),
            "current_snapshot_sha256": current_hash,
            "research_hold": report["research_hold"],
            "source_finality_status": report.get("source_finality_status"),
            "source_finality_verified_assets": report.get("source_finality_verified_assets"),
            "status": report["status"],
        }


def compare_local_remote(local_blob, remote_blob, *, remote_md5=None):
    local = verify_results_blob(local_blob)
    remote = verify_results_blob(remote_blob)
    if remote_md5 and md5(remote_blob).hexdigest() != remote_md5:
        raise RuntimeError("READBACK_REMOTE_MD5_MISMATCH")
    if checksum(local_blob) != checksum(remote_blob):
        raise RuntimeError("READBACK_REMOTE_ZIP_SHA256_MISMATCH")
    if local != remote:
        raise RuntimeError("READBACK_REMOTE_SNAPSHOT_METADATA_MISMATCH")
    return {
        "version": "daily20-drive-readback-v1",
        "status": "READBACK_VERIFIED",
        "research_only": True, "remote_write": False,
        "live_execution": False, "strategy_promoted": False,
        "drive_file_id": EXPECTED_DRIVE_RESULTS_ID,
        "archive_sha256": checksum(remote_blob),
        "archive_bytes": len(remote_blob),
        **{k: v for k, v in local.items() if k != "status"},
        "stability_status": local["status"],
    }


def download_remote(credentials):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    metadata = service.files().get(
        fileId=EXPECTED_DRIVE_RESULTS_ID,
        fields="id,name,mimeType,size,md5Checksum",
        supportsAllDrives=True,
    ).execute()
    if (metadata.get("id") != EXPECTED_DRIVE_RESULTS_ID
            or metadata.get("name") != EXPECTED_DRIVE_RESULTS_NAME
            or metadata.get("mimeType") != "application/zip"
            or int(metadata.get("size", 0)) <= 0
            or int(metadata["size"]) > MAX_RESULTS_SIZE):
        raise RuntimeError("READBACK_UNEXPECTED_DRIVE_TARGET")
    stream = BytesIO()
    downloader = MediaIoBaseDownload(
        stream,
        service.files().get_media(
            fileId=EXPECTED_DRIVE_RESULTS_ID, supportsAllDrives=True),
    )
    done = False
    while not done:
        _, done = downloader.next_chunk()
        if stream.tell() > MAX_RESULTS_SIZE:
            raise RuntimeError("READBACK_STREAM_SIZE_LIMIT")
    return stream.getvalue(), metadata.get("md5Checksum")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local-zip", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    # Authenticate only AFTER the local archive is structurally validated.
    local = Path(args.local_zip).read_bytes()
    verify_results_blob(local)
    from publish_drive import credentials_from_env
    remote, remote_md5 = download_remote(credentials_from_env())
    report = compare_local_remote(local, remote, remote_md5=remote_md5)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"DAILY20_DRIVE_READBACK": report}))


if __name__ == "__main__":
    main()
