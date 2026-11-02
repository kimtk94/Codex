"""Offline tests for durable manual-Save journal; all data synthetic."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manual_save_journal import (
    _atomic_commit, _read, exclusive_ledger, plan_outcome,
    record_manual_outcome, reserve_manual_review, review_reservation,
)
from save_readback_contract import validate_ledger

SF = "006000000000000AAA"
ACCT = "001000000000000AAA"
CONTACT = "003000000000000AAA"
BIZ = "Opp-2099-01-01-222222"
HASH = "a" * 64
INTENT = "b" * 64


def sample():
    return {"version": "sfdc-local-operation-ledger-v1", "entries": []}


def preflight(uid="REQ-test-0001", finger=HASH):
    return {
        "status": "PREPARED_FOR_LIVE_BEFORE_VALUE_CHECK",
        "request_uid": uid, "target_record_id": SF,
        "operation_fingerprint": finger,
        "change_intent_fingerprint": INTENT,
        "save_allowed": False,
    }


def live(finger=HASH):
    return {
        "status": "VERIFIED_LIVE_BEFORE_VALUES",
        "operation_fingerprint": finger,
        "live_before_values_verified": True,
        "fill_allowed": False, "values_filled": False,
        "salesforce_save_allowed": False, "salesforce_save_performed": False,
    }


def approval(uid="REQ-test-0001", finger=HASH):
    return {
        "approved_action": "SAVE_EXISTING_OPPORTUNITY",
        "request_uid": uid, "operation_fingerprint": finger,
        "approved_for_record": SF, "explicit_current_deal_approval": True,
    }


def evidence_start():
    return {"human_executed_write_started": True}


def expected():
    return {
        "opportunity_record_id": SF, "account_record_id": ACCT,
        "contact_record_id": CONTACT, "business_opportunity_id": BIZ,
        "changes": {"Amount": "125.00"},
    }


def refreshed():
    return {
        "source": "Salesforce UI after explicit Save and page reload",
        "reloaded_after_save": True, "record_url_reopened": True,
        "unique_target_page": True,
        "opportunity_record_id": SF, "account_record_id": ACCT,
        "contact_record_id": CONTACT, "business_opportunity_id": BIZ,
        "changed_field_values": {"Amount": "125.00"},
    }


class JournalPureTests(unittest.TestCase):
    def test_without_approval_no_review_reservation(self):
        status, entry = review_reservation(sample(), preflight(), live(), None)
        self.assertEqual(status, "HOLD_EXPLICIT_SAVE_APPROVAL_REQUIRED")
        self.assertIsNone(entry)

    def test_valid_manual_review_reservation_is_not_save_permission(self):
        status, entry = review_reservation(sample(), preflight(), live(), approval())
        self.assertEqual(status, "MANUAL_REVIEW_RESERVED_NO_SAVE")
        self.assertEqual(entry["state"], "PREPARED")
        self.assertIs(entry["save_performed_by_this_module"], False)
        self.assertNotIn("save_allowed", entry)
        validate_ledger({"version": sample()["version"], "entries": [entry]})

    def test_missing_write_start_evidence_rejected(self):
        _, entry = review_reservation(sample(), preflight(), live(), approval())
        ledger = {"version": sample()["version"], "entries": [entry]}
        with self.assertRaises(ValueError):
            plan_outcome(ledger, entry["request_uid"], "EXTERNAL_SAVE_STARTED", {})

    def test_unknown_write_result_can_never_start_again(self):
        _, entry = review_reservation(sample(), preflight(), live(), approval())
        first = {"version": sample()["version"], "entries": [entry]}
        second = plan_outcome(first, entry["request_uid"], "EXTERNAL_SAVE_STARTED", evidence_start())
        unknown = plan_outcome(second, entry["request_uid"], "EXTERNAL_SAVE_OUTCOME_UNKNOWN")
        self.assertEqual(unknown["entries"][0]["state"], "WRITE_OUTCOME_UNKNOWN")
        with self.assertRaises(ValueError):
            plan_outcome(unknown, entry["request_uid"], "EXTERNAL_SAVE_STARTED", evidence_start())
        with self.assertRaises(ValueError):
            plan_outcome(unknown, entry["request_uid"], "CANCEL_REVIEW")

    def test_valid_readback_is_only_review_required_not_verified(self):
        _, entry = review_reservation(sample(), preflight(), live(), approval())
        data = {"version": sample()["version"], "entries": [entry]}
        started = plan_outcome(data, entry["request_uid"], "EXTERNAL_SAVE_STARTED", evidence_start())
        pending = plan_outcome(started, entry["request_uid"], "EXTERNAL_SAVE_OUTCOME_UNKNOWN")
        matched = plan_outcome(pending, entry["request_uid"], "VERIFY_READBACK",
                               {"approved": expected(), "refreshed": refreshed()})
        self.assertEqual(matched["entries"][0]["state"], "READBACK_MATCH_REVIEW_REQUIRED")
        self.assertNotEqual(matched["entries"][0]["state"], "VERIFIED")

    def test_mismatched_post_save_link_keeps_unknown_state(self):
        _, entry = review_reservation(sample(), preflight(), live(), approval())
        first = {"version": sample()["version"], "entries": [entry]}
        started = plan_outcome(first, entry["request_uid"], "EXTERNAL_SAVE_STARTED", evidence_start())
        unknown = plan_outcome(started, entry["request_uid"], "EXTERNAL_SAVE_OUTCOME_UNKNOWN")
        wrong = refreshed()
        wrong["contact_record_id"] = "003000000000001AAA"
        with self.assertRaisesRegex(ValueError, "readback mismatch"):
            plan_outcome(unknown, entry["request_uid"], "VERIFY_READBACK",
                         {"approved": expected(), "refreshed": wrong})
        self.assertEqual(unknown["entries"][0]["state"], "WRITE_OUTCOME_UNKNOWN")

    def test_cancel_only_before_external_write(self):
        _, entry = review_reservation(sample(), preflight(), live(), approval())
        data = {"version": sample()["version"], "entries": [entry]}
        cancelled = plan_outcome(data, entry["request_uid"], "CANCEL_REVIEW")
        self.assertEqual(cancelled["entries"][0]["state"], "CANCELLED")
        with self.assertRaises(ValueError):
            plan_outcome(cancelled, entry["request_uid"], "EXTERNAL_SAVE_STARTED", evidence_start())

    def test_unknown_event_never_changes_ledger(self):
        _, entry = review_reservation(sample(), preflight(), live(), approval())
        data = {"version": sample()["version"], "entries": [entry]}
        with self.assertRaises(ValueError):
            plan_outcome(data, entry["request_uid"], "SAVE_NOW")
        self.assertEqual(data["entries"][0]["state"], "PREPARED")

    def test_missing_record_rejected(self):
        with self.assertRaises(ValueError):
            plan_outcome(sample(), "REQ-other-0001", "CANCEL_REVIEW")


class LocalFileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = self.root / ".sfdc_desktop"
        self.private.mkdir()
        self.path = self.private / "operation_ledger_private.json"
        self.path.write_text(json.dumps(sample()), encoding="utf-8")
        self.home_patch = patch("manual_save_journal.Path.home", return_value=self.root)
        self.home_patch.start()

    def tearDown(self):
        self.home_patch.stop()
        self.temp.cleanup()

    def test_reserve_reviewed_operation_durable(self):
        result = reserve_manual_review(self.path, preflight(), live(), approval())
        self.assertEqual(result["status"], "MANUAL_REVIEW_RESERVED_NO_SAVE")
        self.assertFalse(result["save_allowed"])
        rows = _read(self.path)["entries"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "PREPARED")
        self.assertFalse((self.private / "operation_ledger_private.json.lock").exists())

    def test_reservation_without_approval_does_not_modify_ledger(self):
        before = self.path.read_bytes()
        result = reserve_manual_review(self.path, preflight(), live(), None)
        self.assertEqual(result["status"], "HOLD_EXPLICIT_SAVE_APPROVAL_REQUIRED")
        self.assertEqual(self.path.read_bytes(), before)

    def test_second_attempt_same_uid_rejected(self):
        reserve_manual_review(self.path, preflight(), live(), approval())
        r = reserve_manual_review(self.path, preflight(), live(), approval())
        self.assertEqual(r["status"], "HOLD_DUPLICATE_OR_IN_FLIGHT_OPERATION")
        self.assertEqual(len(_read(self.path)["entries"]), 1)

    def test_fresh_uid_same_change_intent_rejected(self):
        reserve_manual_review(self.path, preflight(), live(), approval())
        r = reserve_manual_review(self.path, preflight("REQ-test-0002", "c"*64),
                                  live("c"*64), approval("REQ-test-0002", "c"*64))
        self.assertEqual(r["status"], "HOLD_DUPLICATE_OR_IN_FLIGHT_OPERATION")
        self.assertEqual(len(_read(self.path)["entries"]), 1)

    def test_stale_directory_lock_fails_closed(self):
        lock = self.private / "operation_ledger_private.json.lock"
        lock.mkdir()
        try:
            with self.assertRaises(RuntimeError):
                reserve_manual_review(self.path, preflight(), live(), approval())
            self.assertEqual(_read(self.path)["entries"], [])
        finally:
            lock.rmdir()

    def test_missing_ledger_fails_closed(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            reserve_manual_review(self.path, preflight(), live(), approval())
        self.assertFalse(self.path.exists())

    def test_corrupt_ledger_fails_closed(self):
        self.path.write_text("{bad json", encoding="utf-8")
        with self.assertRaises(ValueError):
            reserve_manual_review(self.path, preflight(), live(), approval())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{bad json")

    def test_only_dedicated_private_path_allowed(self):
        wrong = self.private / "other_customer_data.json"
        wrong.write_text(json.dumps(sample()), encoding="utf-8")
        with self.assertRaises(ValueError):
            with exclusive_ledger(wrong):
                pass

    def test_failed_atomic_rename_preserves_previous_ledger(self):
        before = self.path.read_bytes()
        with patch("manual_save_journal.os.replace", side_effect=OSError("synthetic disk error")):
            with self.assertRaises(OSError):
                reserve_manual_review(self.path, preflight(), live(), approval())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.private.glob(".operation_ledger_*.tmp")), [])

    def test_manual_outcome_recorded_without_salesforce_calls(self):
        reserve_manual_review(self.path, preflight(), live(), approval())
        r = record_manual_outcome(self.path, "REQ-test-0001", "CANCEL_REVIEW")
        self.assertEqual(r["status"], "CANCELLED")
        self.assertIs(r["save_allowed"], False)
        self.assertEqual(_read(self.path)["entries"][0]["state"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
