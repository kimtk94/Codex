import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import archive_candidate_once as archive
from candidate_compare import compare_archives
from test_candidate_compare import bundle, frame


TARGET = "candidate_slot_fixture_12345"
SESSION = "2026-10-30"
RUN = "123456789"


class FakeClient:
    def __init__(self, seed):
        self.data = seed
        self.meta = {
            "id": TARGET, "name": f"UNFILLED_market_candidate_{SESSION}.zip",
            "parents": [archive.CANDIDATE_FOLDER_ID], "mimeType": "application/zip",
            "trashed": False, "capabilities": {"canEdit": True},
            "permissions": [{"type": "user", "role": "owner"},
                            {"type": "user", "role": "writer"}],
        }
        self.writes = []
        self.corrupt = False

    def metadata(self, target):
        if target != TARGET:
            raise AssertionError("unexpected target")
        return copy.deepcopy(self.meta)

    def download(self, target):
        if target != TARGET:
            raise AssertionError("unexpected download")
        return self.data

    def write_bytes(self, target, data):
        if target != TARGET:
            raise AssertionError("unexpected write")
        self.writes.append(("bytes", target))
        self.data = data + b"bad" if self.corrupt else data

    def rename(self, target, name):
        if target != TARGET:
            raise AssertionError("unexpected rename")
        self.writes.append(("name", target))
        self.meta["name"] = name


class PrivateArchiveContracts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        old, new = Path(temp.name)/"old.zip", Path(temp.name)/"candidate.zip"
        bundle(old, frame())
        bundle(new, frame(periods=35))
        self.original, self.candidate = old.read_bytes(), new.read_bytes()
        self.audit = compare_archives(old, new)
        p = patch.object(archive, "ORIGINAL_SHA256", archive.digest(self.original))
        p.start()
        self.addCleanup(p.stop)
        self.client = FakeClient(self.original)

    def store(self, **kwargs):
        args = dict(original=self.original, candidate=self.candidate, audit=self.audit,
                    target_id=TARGET, expected_session=SESSION, run_id=RUN)
        args.update(kwargs)
        return archive.save_once(self.client, **args)

    def test_preflight_no_write_and_missing_parent_diagnosed(self):
        report = archive.preflight(self.client, TARGET, SESSION)
        self.assertTrue(report["eligible_for_archive"])
        self.assertTrue(report["seed_sha256_matches"])
        self.assertTrue(report["read_only"])
        self.assertEqual(self.client.writes, [])
        self.client.meta.pop("parents")
        report = archive.preflight(self.client, TARGET, SESSION)
        self.assertFalse(report["candidate_slot_checks"]["parent_visible"])
        self.assertFalse(report["candidate_slot_checks"]["parent_matches"])
        self.assertFalse(report["eligible_for_archive"])
        self.assertTrue(report["seed_sha256_matches"])
        self.assertEqual(self.client.writes, [])
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_OR_CONSUMED"):
            self.store()
        self.assertEqual(self.client.writes, [])

    def test_preflight_missing_capability_or_permissions_never_eligible(self):
        self.client.meta.pop("capabilities")
        self.client.meta.pop("permissions")
        report = archive.preflight(self.client, TARGET, SESSION)
        checks = report["candidate_slot_checks"]
        self.assertFalse(checks["edit_capability_visible"])
        self.assertFalse(checks["can_edit"])
        self.assertFalse(checks["permissions_visible"])
        self.assertFalse(report["eligible_for_archive"])
        self.assertEqual(self.client.writes, [])

    def test_preflight_rejects_canonical_id(self):
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_CANDIDATE_TARGET"):
            archive.preflight(self.client, archive.ORIGINAL_ID, SESSION)
        self.assertEqual(self.client.writes, [])

    def test_save_once_verified_readback_and_no_reuse(self):
        r = self.store()
        self.assertEqual(self.client.data, self.candidate)
        self.assertEqual(self.client.writes, [("bytes", TARGET), ("name", TARGET)])
        self.assertTrue(r["remote_sha256_verified"])
        self.assertTrue(r["private_candidate_archive_persisted"])
        self.assertFalse(r["original_drive_zip_replaced"])
        self.assertFalse(r["ready_for_pit_training"])
        self.assertEqual(r["approved_rows_for_merge"], 0)
        self.assertEqual(r["filename"], f"market_candidate_HOLD_{SESSION}_GH{RUN}.zip")
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_OR_CONSUMED"):
            self.store()
        self.assertEqual(len(self.client.writes), 2)

    def test_canonical_target_and_wrong_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_CANDIDATE_TARGET"):
            self.store(target_id=archive.ORIGINAL_ID)
        self.client.meta["parents"] = ["wrong"]
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_OR_CONSUMED"):
            self.store()
        self.assertEqual(self.client.writes, [])

    def test_public_permission_and_modified_seed_rejected(self):
        self.client.meta["permissions"].append({"type": "anyone", "role": "reader"})
        with self.assertRaisesRegex(ValueError, "NOT_FILE_SCOPED"):
            self.store()
        self.client.meta["permissions"].pop()
        self.client.data = b"not the verified seed"
        with self.assertRaisesRegex(ValueError, "SEED_CHANGED_OR_CONSUMED"):
            self.store()
        self.assertEqual(self.client.writes, [])

    def test_audit_mismatch_and_wrong_session_rejected(self):
        wrong = dict(self.audit, candidate_sha256="0"*64)
        with self.assertRaisesRegex(ValueError, "MISSING_OR_UNSAFE"):
            self.store(audit=wrong)
        with self.assertRaisesRegex(ValueError, "SESSION_OR_FRED"):
            self.store(expected_session="2026-11-24")
        self.assertEqual(self.client.writes, [])

    def test_readback_mismatch_does_not_rename_or_retry(self):
        self.client.corrupt = True
        with self.assertRaisesRegex(RuntimeError, "REMOTE_SHA256_MISMATCH"):
            self.store()
        self.assertEqual(self.client.writes, [("bytes", TARGET)])
        self.assertTrue(self.client.meta["name"].startswith("UNFILLED_"))
        with self.assertRaisesRegex(ValueError, "SEED_CHANGED_OR_CONSUMED"):
            self.store()
        self.assertEqual(len(self.client.writes), 1)

    def test_incomplete_audit_and_nonhold_asset_rejected(self):
        for rows in (self.audit["assets"][:-1], [
            dict(r, release="APPROVED") if i == 0 else r
            for i, r in enumerate(self.audit["assets"])
        ]):
            with self.assertRaisesRegex(ValueError, "INCOMPLETE_CANDIDATE_ASSET_AUDIT"):
                self.store(audit=dict(self.audit, assets=rows))
        self.assertEqual(self.client.writes, [])


if __name__ == "__main__":
    unittest.main()
