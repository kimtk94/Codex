"""G12 synthetic cross-store outbox regression: no live DB or Sheet."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from g12_outbox_sim import (
    DeliveryConflict, FakeCASheets, Outbox, deliver_once,
)
from g16_synthetic_pipeline import IsolationError


def fixture(stage="SYN-SIF", prepayment=False, action="FOLLOWUP"):
    return {"stage": stage, "prepayment": prepayment, "action": action}


class G12OutboxTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tmp = tempfile.TemporaryDirectory(prefix="g12-outbox-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "outbox.sqlite3"
        self.outbox = Outbox(self.path)
        self.addCleanup(self.outbox.close)
        self.sheet = FakeCASheets()

    def queue(self, pid="TEST-A", revision=1, expected=0, payload=None):
        return self.outbox.enqueue(pid, revision, expected, payload or fixture())

    def test_001_committed_intent_not_yet_published(self):
        self.queue()
        self.assertEqual(self.outbox.count(False), 1)
        self.assertEqual(self.sheet.physical_writes, 0)

    def test_002_success_acks_and_writes(self):
        self.queue()
        self.assertEqual(deliver_once(self.outbox, self.sheet), (1, 0))
        self.assertEqual(self.outbox.count(True), 1)
        self.assertEqual(self.sheet.rows["TEST-A"][0], 1)

    def test_003_repeat_idempotent(self):
        key1 = self.queue()
        self.assertEqual(key1, self.queue())
        self.assertEqual(self.outbox.count(), 1)
        deliver_once(self.outbox, self.sheet)
        self.assertEqual(deliver_once(self.outbox, self.sheet), (0, 0))
        self.assertEqual(self.sheet.physical_writes, 1)

    def test_004_sheet_fails_before_write(self):
        key = self.queue()
        self.sheet.fail_before.add(key)
        with self.assertRaisesRegex(RuntimeError, "before_write_failure"):
            deliver_once(self.outbox, self.sheet)
        self.assertEqual(self.outbox.count(False), 1)
        self.assertEqual(self.sheet.physical_writes, 0)
        self.assertEqual(deliver_once(self.outbox, self.sheet), (1, 0))

    def test_005_sheet_response_lost_after_commit(self):
        key = self.queue()
        self.sheet.fail_after.add(key)
        with self.assertRaisesRegex(RuntimeError, "response_lost"):
            deliver_once(self.outbox, self.sheet)
        self.assertEqual(self.outbox.count(False), 1)
        self.assertEqual(self.sheet.physical_writes, 1)
        self.assertEqual(deliver_once(self.outbox, self.sheet), (0, 1))
        self.assertEqual(self.sheet.physical_writes, 1)
        self.assertEqual(self.outbox.count(True), 1)

    def test_006_sqlite_ack_failure_retries_sheet_receipt(self):
        key = self.queue()
        self.outbox.fail_ack_once.add(key)
        with self.assertRaisesRegex(RuntimeError, "sqlite_ack_failure"):
            deliver_once(self.outbox, self.sheet)
        self.assertEqual(self.sheet.physical_writes, 1)
        self.assertEqual(self.outbox.count(False), 1)
        self.assertEqual(deliver_once(self.outbox, self.sheet), (0, 1))
        self.assertEqual(self.sheet.physical_writes, 1)

    def test_007_restart_reuses_durable_outbox(self):
        self.queue()
        self.outbox.close()
        self.outbox = Outbox(self.path)
        self.assertEqual(self.outbox.count(False), 1)
        self.assertEqual(deliver_once(self.outbox, self.sheet), (1, 0))

    def test_008_manual_edit_conflict_fails_closed(self):
        self.queue()
        self.sheet.manual_edit("TEST-A")
        with self.assertRaisesRegex(DeliveryConflict, "manual edit"):
            deliver_once(self.outbox, self.sheet)
        self.assertEqual(self.outbox.count(False), 1)
        self.assertEqual(self.sheet.physical_writes, 0)
        self.assertEqual(self.sheet.rows["TEST-A"][0], 1)

    def test_009_next_revision_after_delivery(self):
        self.queue()
        deliver_once(self.outbox, self.sheet)
        self.queue(revision=2, expected=1, payload=fixture("SYN-QC", False, "QC"))
        self.assertEqual(deliver_once(self.outbox, self.sheet), (1, 0))
        self.assertEqual(self.sheet.rows["TEST-A"][0], 2)
        self.assertEqual(self.sheet.rows["TEST-A"][1]["stage"], "SYN-QC")

    def test_010_two_projects_partial_delivery_then_recovery(self):
        self.queue("TEST-A")
        kb = self.queue("TEST-B")
        self.sheet.fail_before.add(kb)
        with self.assertRaisesRegex(RuntimeError, "before_write_failure"):
            deliver_once(self.outbox, self.sheet)
        self.assertEqual(self.sheet.physical_writes, 1)
        self.assertEqual(self.outbox.count(False), 1)
        self.assertEqual(deliver_once(self.outbox, self.sheet), (1, 0))
        self.assertEqual(self.outbox.count(True), 2)
        self.assertEqual(self.sheet.physical_writes, 2)

    def test_011_conflicting_same_revision_denied(self):
        self.queue()
        with self.assertRaises(DeliveryConflict):
            self.queue(payload=fixture("SYN-OTHER", True, "SKIP"))
        self.assertEqual(self.outbox.count(), 1)

    def test_012_conflicting_expected_version_denied(self):
        self.queue()
        with self.assertRaises(DeliveryConflict):
            self.queue(expected=1)

    def test_013_production_project_denied(self):
        with self.assertRaises(IsolationError):
            self.queue(pid="AMEA2026100001")

    def test_014_production_path_denied(self):
        with self.assertRaises(IsolationError):
            Outbox(Path("/var/tmp/css-runtime.sqlite3"))

    def test_015_non_synthetic_payload_denied(self):
        for payload in [
            {"stage": "Real SIF", "prepayment": True, "action": "SKIP"},
            {"stage": "SYN-SIF", "prepayment": True, "action": "SEND_MAIL"},
            {"stage": "SYN-SIF", "prepayment": True, "action": "SKIP", "email": "customer@example.test"},
        ]:
            with self.subTest(payload=sorted(payload)), self.assertRaises(IsolationError):
                self.queue(payload=payload)

    def test_016_corrupted_outbox_payload_rejected(self):
        self.queue()
        self.outbox.db.execute("UPDATE outbox SET payload=? WHERE project='TEST-A'",
                               ('{"stage":"SYN-TAMPER","prepayment":false,"action":"NONE"}',))
        with self.assertRaisesRegex(IsolationError, "integrity mismatch"):
            deliver_once(self.outbox, self.sheet)
        self.assertEqual(self.sheet.physical_writes, 0)

    def test_017_receipt_payload_collision_denied(self):
        key = self.queue()
        self.sheet.receipts[key] = "fake-other-digest"
        with self.assertRaises(DeliveryConflict):
            deliver_once(self.outbox, self.sheet)

    def test_018_env_guard_enforced(self):
        self.queue()
        with patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "0"}):
            with self.assertRaises(IsolationError):
                deliver_once(self.outbox, self.sheet)

    def test_019_invalid_version_and_schema_denied(self):
        for revision, expected in [(0, 0), (True, 0), (1, -1), (1, False)]:
            with self.subTest(revision=revision, expected=expected), self.assertRaises(IsolationError):
                self.queue(revision=revision, expected=expected)

    def test_020_independent_manual_skip_payload(self):
        self.queue(payload=fixture("SYN-SIF", True, "SKIP"))
        deliver_once(self.outbox, self.sheet)
        self.assertEqual(self.sheet.rows["TEST-A"][1]["action"], "SKIP")
        self.assertEqual(self.outbox.count(True), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
