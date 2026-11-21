"""Offline SHA256 and snapshot-governance tests for Drive post-upload readback."""
from __future__ import annotations

from hashlib import md5, sha256
from io import BytesIO
import json
import unittest
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from stability_drive_readback import (
    EXPECTED_STABILITY_VERSION, compare_local_remote, verify_results_blob,
)


def signed_archive(*, change=None, compress=ZIP_STORED, archive_report=True):
    session = "2026-11-20"
    snap_name = "research/stability/snapshots/" + session + ".json"
    snap = json.dumps({
        "schema": EXPECTED_STABILITY_VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "feature_count": 21, "models": {},
    }, sort_keys=True).encode()
    status = "SEALED_NEW_SESSION"
    report = {
        "version": EXPECTED_STABILITY_VERSION, "session": session,
        "research_only": True, "production_writes": False,
        "promotional_attribution_allowed": False, "strategy_promoted": False,
        "research_hold": False, "status": status,
        "frozen_sessions_preserved": 1,
        "current_session_has_original_snapshot": True,
        "frozen_snapshot_sha256": sha256(snap).hexdigest(),
    }
    files = {snap_name: snap}
    if archive_report:
        files["research/stability/report.json"] = json.dumps(report).encode()
    manifest = {
        "format": "kalman-daily20-drive-v1", "research_only": True,
        "production_writes": False, "oos_score_count": 20,
        "data_expected_last_closed_xnys": session,
        "stability_status": status, "stability_research_hold": False,
        "payload_hashes_sha256": {
            name: sha256(payload).hexdigest() for name, payload in files.items()
        },
    }
    if change == "bad_current_hash":
        report["frozen_snapshot_sha256"] = "a" * 64
        files["research/stability/report.json"] = json.dumps(report).encode()
        manifest["payload_hashes_sha256"]["research/stability/report.json"] = sha256(
            files["research/stability/report.json"]).hexdigest()
    if change == "bad_member":
        files[snap_name] = snap.replace(b'"research_only": true',
                                      b'"research_only": false', 1)
    if change == "bad_manifest_status":
        manifest["stability_status"] = "REPLAY_DRIFT_RESEARCH_HOLD"
    if change == "bad_snapshot_count":
        report["frozen_sessions_preserved"] = 2
        files["research/stability/report.json"] = json.dumps(report).encode()
        manifest["payload_hashes_sha256"]["research/stability/report.json"] = sha256(
            files["research/stability/report.json"]).hexdigest()
    mem = BytesIO()
    with ZipFile(mem, "w", compression=compress) as z:
        for key, payload in files.items():
            z.writestr(key, payload)
        z.writestr("drive_manifest.json", json.dumps(manifest))
    return mem.getvalue()


class DriveReadbackTests(unittest.TestCase):
    def test_byte_identical_remote_archive_passes(self):
        data = signed_archive()
        report = compare_local_remote(data, data, remote_md5=md5(data).hexdigest())
        self.assertEqual(report["status"], "SEALED_NEW_SESSION")
        self.assertEqual(report["snapshot_count"], 1)
        self.assertEqual(report["archive_sha256"], sha256(data).hexdigest())
        self.assertFalse(report["remote_write"])

    def test_bad_member_hash_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "READBACK_MEMBER_SHA256_MISMATCH"):
            verify_results_blob(signed_archive(change="bad_member"))

    def test_stability_report_required(self):
        with self.assertRaisesRegex(RuntimeError, "READBACK_STABILITY_REPORT_MISSING"):
            verify_results_blob(signed_archive(archive_report=False))

    def test_incorrect_original_snapshot_hash_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "READBACK_FROZEN_CURRENT_HASH_INVALID"):
            verify_results_blob(signed_archive(change="bad_current_hash"))

    def test_snapshot_count_mismatch_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "READBACK_FROZEN_SNAPSHOT_COUNT_MISMATCH"):
            verify_results_blob(signed_archive(change="bad_snapshot_count"))

    def test_manifest_and_stability_report_disagreement_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "READBACK_STABILITY_GOVERNANCE_INVALID"):
            verify_results_blob(signed_archive(change="bad_manifest_status"))

    def test_same_content_but_different_archive_bytes_rejected(self):
        left = signed_archive(compress=ZIP_STORED)
        right = signed_archive(compress=ZIP_DEFLATED)
        self.assertNotEqual(left, right)
        with self.assertRaisesRegex(RuntimeError, "READBACK_REMOTE_ZIP_SHA256_MISMATCH"):
            compare_local_remote(left, right)

    def test_incorrect_remote_md5_rejected(self):
        data = signed_archive()
        with self.assertRaisesRegex(RuntimeError, "READBACK_REMOTE_MD5_MISMATCH"):
            compare_local_remote(data, data, remote_md5="0" * 32)


if __name__ == "__main__":
    unittest.main()
