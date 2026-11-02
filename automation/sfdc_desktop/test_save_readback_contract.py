"""Synthetic regressions for no-Save review, duplicate protection and reloaded readback."""
import unittest

from save_readback_contract import (
    validate_ledger, review_save_contract, evaluate_post_save_readback,
)

SF = "006000000000000AAA"
ACCT = "001000000000000AAA"
CONTACT = "003000000000000AAA"
BIZ = "Opp-2099-01-01-222222"
HASH = "a" * 64
INTENT = "b" * 64


def ledger(entries=None):
    return {"version": "sfdc-local-operation-ledger-v1",
            "entries": [] if entries is None else entries}


def preflight():
    return {"status": "PREPARED_FOR_LIVE_BEFORE_VALUE_CHECK",
            "request_uid": "REQ-synthetic-001",
            "target_record_id": SF, "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT,
            "save_allowed": False}


def live():
    return {"status": "VERIFIED_LIVE_BEFORE_VALUES",
            "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT,
            "live_before_values_verified": True,
            "fill_allowed": False, "values_filled": False,
            "salesforce_save_allowed": False, "salesforce_save_performed": False}


def approval():
    return {"approved_action": "SAVE_EXISTING_OPPORTUNITY",
            "request_uid": "REQ-synthetic-001",
            "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT,
            "approved_for_record": SF,
            "explicit_current_deal_approval": True}


def approved():
    return {"opportunity_record_id": SF, "account_record_id": ACCT,
            "contact_record_id": CONTACT, "business_opportunity_id": BIZ,
            "changes": {"Amount": "200.00", "Close Date": "2099-01-02"}}


def refreshed():
    return {"source": "Salesforce UI after explicit Save and page reload",
            "reloaded_after_save": True, "record_url_reopened": True,
            "unique_target_page": True,
            "opportunity_record_id": SF, "account_record_id": ACCT,
            "contact_record_id": CONTACT, "business_opportunity_id": BIZ,
            "changed_field_values": {"Amount": "200.00", "Close Date": "2099-01-02"}}


class LedgerSafetyTests(unittest.TestCase):
    def test_empty_versioned_ledger_valid(self):
        self.assertEqual(validate_ledger(ledger()), [])

    def test_missing_ledger_rejected(self):
        with self.assertRaises(ValueError):
            validate_ledger(None)

    def test_corrupt_ledger_rejected(self):
        with self.assertRaises(ValueError):
            validate_ledger({"entries": []})

    def test_duplicate_same_uid_rejected(self):
        e = {"request_uid": "REQ-synthetic-001",
             "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT, "state": "PENDING_WRITE"}
        with self.assertRaises(ValueError):
            validate_ledger(ledger([e, dict(e)]))

    def test_duplicate_same_fingerprint_rejected(self):
        a = {"request_uid": "REQ-synthetic-001",
             "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT, "state": "VERIFIED"}
        b = {"request_uid": "REQ-synthetic-002",
             "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT, "state": "HOLD"}
        with self.assertRaises(ValueError):
            validate_ledger(ledger([a, b]))

    def test_identical_intent_different_uid_rejected(self):
        a = {"request_uid": "REQ-synthetic-001",
             "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT,
             "state": "VERIFIED"}
        b = {"request_uid": "REQ-synthetic-002",
             "operation_fingerprint": "c" * 64, "change_intent_fingerprint": INTENT,
             "state": "PREPARED"}
        with self.assertRaises(ValueError):
            validate_ledger(ledger([a, b]))

    def test_unknown_state_rejected(self):
        e = {"request_uid": "REQ-synthetic-001",
             "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT, "state": "CAN_SAVE"}
        with self.assertRaises(ValueError):
            validate_ledger(ledger([e]))


class SaveReviewTests(unittest.TestCase):
    def test_no_approval_remains_hold(self):
        r = review_save_contract(preflight(), live(), None, ledger())
        self.assertEqual(r["status"], "HOLD_EXPLICIT_SAVE_APPROVAL_REQUIRED")
        self.assertFalse(r["save_allowed"])

    def test_valid_approval_still_never_executes_save(self):
        r = review_save_contract(preflight(), live(), approval(), ledger())
        self.assertEqual(r["status"], "READY_FOR_SEPARATE_MANUAL_SAVE_REVIEW_NOT_EXECUTION")
        self.assertFalse(r["save_allowed"])
        self.assertFalse(r["salesforce_save_performed"])

    def test_same_intent_under_fresh_uid_blocks(self):
        prior = {"request_uid": "REQ-synthetic-prior",
                 "operation_fingerprint": "c" * 64,
                 "change_intent_fingerprint": INTENT, "state": "VERIFIED"}
        result = review_save_contract(preflight(), live(), approval(), ledger([prior]))
        self.assertEqual(result["status"], "HOLD_DUPLICATE_OR_IN_FLIGHT_OPERATION")

    def test_existing_inflight_uid_blocks_retry(self):
        e = {"request_uid": "REQ-synthetic-001",
             "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT, "state": "WRITE_OUTCOME_UNKNOWN"}
        r = review_save_contract(preflight(), live(), approval(), ledger([e]))
        self.assertEqual(r["status"], "HOLD_DUPLICATE_OR_IN_FLIGHT_OPERATION")

    def test_previous_complete_record_blocks_retry(self):
        e = {"request_uid": "REQ-synthetic-001",
             "operation_fingerprint": HASH, "change_intent_fingerprint": INTENT, "state": "VERIFIED"}
        r = review_save_contract(preflight(), live(), approval(), ledger([e]))
        self.assertEqual(r["status"], "HOLD_DUPLICATE_OR_IN_FLIGHT_OPERATION")

    def test_wrong_target_approval_blocks(self):
        a = approval()
        a["approved_for_record"] = "006000000000001AAA"
        self.assertEqual(review_save_contract(preflight(), live(), a, ledger())["status"],
                         "HOLD_EXPLICIT_SAVE_APPROVAL_REQUIRED")

    def test_fingerprint_mismatch_blocks(self):
        v = live()
        v["operation_fingerprint"] = "b" * 64
        self.assertEqual(review_save_contract(preflight(), v, approval(), ledger())["status"],
                         "HOLD_PREFLIGHT_OR_LIVE_EVIDENCE")

    def test_filled_form_never_treated_as_before_verification(self):
        v = live()
        v["values_filled"] = True
        self.assertEqual(review_save_contract(preflight(), v, approval(), ledger())["status"],
                         "HOLD_PREFLIGHT_OR_LIVE_EVIDENCE")

    def test_empty_or_unverified_preflight_blocks(self):
        self.assertEqual(review_save_contract(None, live(), approval(), ledger())["status"],
                         "HOLD_MISSING_PREFLIGHT")


class ReloadedReadbackTests(unittest.TestCase):
    def test_matching_reloaded_fields_still_need_review(self):
        self.assertEqual(evaluate_post_save_readback(approved(), refreshed()),
                         "READBACK_FIELDS_AND_LINKS_MATCH_REVIEW_REQUIRED")

    def test_no_reloaded_page_blocks(self):
        r = refreshed()
        r["reloaded_after_save"] = False
        self.assertEqual(evaluate_post_save_readback(approved(), r),
                         "HOLD_READBACK_NOT_RELOADED")

    def test_wrong_account_id_blocks(self):
        r = refreshed()
        r["account_record_id"] = "001000000000001AAA"
        self.assertEqual(evaluate_post_save_readback(approved(), r),
                         "HOLD_READBACK_IDENTITY_CHANGED")

    def test_wrong_contact_id_blocks(self):
        r = refreshed()
        r["contact_record_id"] = "003000000000001AAA"
        self.assertEqual(evaluate_post_save_readback(approved(), r),
                         "HOLD_READBACK_IDENTITY_CHANGED")

    def test_wrong_business_id_blocks(self):
        r = refreshed()
        r["business_opportunity_id"] = "Opp-2099-01-01-999999"
        self.assertEqual(evaluate_post_save_readback(approved(), r),
                         "HOLD_READBACK_IDENTITY_CHANGED")

    def test_mismatch_changed_values_blocks(self):
        r = refreshed()
        r["changed_field_values"]["Amount"] = "150.00"
        self.assertEqual(evaluate_post_save_readback(approved(), r),
                         "HOLD_READBACK_CHANGED_VALUES_DIFFER")

    def test_missing_field_blocks(self):
        r = refreshed()
        del r["changed_field_values"]["Close Date"]
        self.assertEqual(evaluate_post_save_readback(approved(), r),
                         "HOLD_READBACK_CHANGED_FIELD_SET_MISMATCH")

    def test_no_actual_approved_changes_blocks(self):
        a = approved()
        a["changes"] = {}
        self.assertEqual(evaluate_post_save_readback(a, refreshed()),
                         "HOLD_READBACK_CHANGED_VALUES_MISSING")


if __name__ == "__main__":
    unittest.main()
