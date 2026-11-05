"""Read-only Salesforce operation journal health test: synthetic files only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inspect_save_journal import summarize

def ledger(entries=()):
    return {"version": "sfdc-local-operation-ledger-v1", "entries": list(entries)}

def entry(uid, state, digit):
    return {
        "request_uid": "REQ-synthetic-" + uid,
        "operation_fingerprint": digit * 64,
        "change_intent_fingerprint": chr(ord(digit) + 1) * 64,
        "state": state,
    }

class JournalInspectorTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = Path(self.t.name)
        self.private = self.home / ".sfdc_desktop"
        self.private.mkdir()
        self.path = self.private / "operation_ledger_private.json"
        self.path.write_text(json.dumps(ledger()), encoding="utf-8")
        self.mock = patch("manual_save_journal.Path.home", return_value=self.home)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.t.cleanup()

    def test_empty_ledger_summary_not_write_permission(self):
        raw = self.path.read_bytes()
        result = summarize(self.path)
        self.assertEqual(result["status"], "LEDGER_READ_ONLY_VALID")
        self.assertEqual(result["total_requests"], 0)
        self.assertFalse(result["save_allowed"])
        self.assertEqual(self.path.read_bytes(), raw)

    def test_prepared_review_is_not_a_completed_save(self):
        self.path.write_text(json.dumps(ledger([entry("001", "PREPARED", "a")])), encoding="utf-8")
        r = summarize(self.path)
        self.assertEqual(r["state_counts"]["PREPARED"], 1)
        self.assertEqual(r["unresolved_operation_count"], 0)
        self.assertFalse(r["save_allowed"])

    def test_unknown_result_requires_manual_recovery(self):
        self.path.write_text(json.dumps(ledger([entry("002", "WRITE_OUTCOME_UNKNOWN", "b")])),
                             encoding="utf-8")
        r = summarize(self.path)
        self.assertEqual(r["status"], "HOLD_MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(r["unresolved_operation_count"], 1)

    def test_unreviewed_matching_readback_is_still_hold(self):
        self.path.write_text(json.dumps(ledger([entry("003", "READBACK_MATCH_REVIEW_REQUIRED", "c")])),
                             encoding="utf-8")
        r = summarize(self.path)
        self.assertEqual(r["status"], "HOLD_MANUAL_RECOVERY_REQUIRED")

    def test_stale_lock_requires_manual_recovery(self):
        (self.private / "operation_ledger_private.json.lock").mkdir()
        self.assertEqual(summarize(self.path)["status"], "HOLD_MANUAL_RECOVERY_REQUIRED")

    def test_summary_never_exposes_source_ids_or_record_fields(self):
        row = entry("004", "PENDING_WRITE", "d")
        row["customer_note"] = "PRIVATE CUSTOMER DATA"
        self.path.write_text(json.dumps(ledger([row])), encoding="utf-8")
        text = json.dumps(summarize(self.path))
        self.assertNotIn("PRIVATE CUSTOMER DATA", text)
        self.assertNotIn("REQ-synthetic-004", text)
        self.assertNotIn("d" * 64, text)

    def test_missing_ledger_does_not_auto_initialize(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            summarize(self.path)
        self.assertFalse(self.path.exists())

    def test_corrupt_ledger_rejected(self):
        self.path.write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            summarize(self.path)


if __name__ == "__main__":
    unittest.main()
