"""Synthetic regressions for fail-closed Salesforce compare-and-swap before-value gate."""
import unittest

from verify_existing_live_before import inspect_request, evaluate_before, run, enforce_clean_ledger

SF = "006000000000000AAA"
ACCOUNT = "001000000000000AAA"
CONTACT = "003000000000000AAA"
BUSINESS = "Opp-2099-01-01-222222"


def req():
    return {
        "request_uid": "REQ-beforetest-001",
        "mode": "EXISTING_OPPORTUNITY_FILL_ONLY",
        "reviewed_current_deal_values": True,
        "target_opportunity_record_id": SF,
        "business_opportunity_id": BUSINESS,
        "expected_account_record_id": ACCOUNT,
        "expected_contact_record_id": CONTACT,
        "expected_before_values": {"Amount": "100.00", "Close Date": "01/02/2099"},
        "changes": {"Amount": "200.00", "Close Date": "2099-01-03"},
        "save_allowed": False,
    }


def bridge():
    return {
        "version": "live-related-quote-report-bridge-v1",
        "status": "VERIFIED_BY_LIVE_QUOTATION_REPORT",
        "identity_verified": True,
        "opportunity_record_id": SF,
        "business_opportunity_id": BUSINESS,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def lookups():
    return {
        "account_contact_field_links_verified": True,
        "opportunity_record_id": SF,
        "account_record_id": ACCOUNT,
        "contact_record_id": CONTACT,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
    }


def preflight():
    return {"save_allowed": False, "changed_fields": ["Amount", "Close Date"]}


class UnreviewedDoesNotTouchSalesforce(unittest.TestCase):
    def test_unreviewed_template_hold(self):
        r = req()
        r["reviewed_current_deal_values"] = False
        r["changes"] = {}
        r["expected_before_values"] = {}
        result = run(r, None, None, ())
        self.assertEqual(result["status"], "HOLD_REVIEW_REQUIRED")
        self.assertFalse(result["fill_allowed"])

    def test_no_changes_even_if_reviewed_hold(self):
        r = req()
        r["changes"] = {}
        self.assertEqual(inspect_request(r), "HOLD_REVIEW_REQUIRED")

    def test_unverified_description_live_field_hold(self):
        r = req()
        r["changes"] = {"Progress Description": "Updated"}
        self.assertEqual(inspect_request(r), "HOLD_UNSUPPORTED_FIELD_LIVE_READ")

    def test_reviewed_but_no_browser_is_not_verified(self):
        result = run(req(), bridge(), lookups(), ())
        self.assertEqual(result["status"], "HOLD_LIVE_READ_NOT_EXECUTED")
        self.assertFalse(result["live_before_values_verified"])
        self.assertFalse(result["salesforce_save_allowed"])

    def test_duplicate_request_uid_fails_offline(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            run(req(), bridge(), lookups(), ["REQ-beforetest-001"])

    def test_wrong_contact_id_fails_offline(self):
        r = req()
        r["expected_contact_record_id"] = "003000000000001AAA"
        with self.assertRaises(ValueError):
            run(r, bridge(), lookups(), ())


class VersionedLedgerFailClosed(unittest.TestCase):
    def test_missing_ledger_fails(self):
        with self.assertRaises(ValueError):
            enforce_clean_ledger(req(), bridge(), lookups(), None)

    def test_empty_ledger_allows_offline_preflight_only(self):
        result, prior = enforce_clean_ledger(
            req(), bridge(), lookups(),
            {"version": "sfdc-local-operation-ledger-v1", "entries": []})
        self.assertEqual(prior, [])
        self.assertFalse(result["save_allowed"])

    def test_same_intent_under_another_uid_fails(self):
        empty = {"version": "sfdc-local-operation-ledger-v1", "entries": []}
        preflight, _ = enforce_clean_ledger(req(), bridge(), lookups(), empty)
        changed = req()
        changed["request_uid"] = "REQ-beforetest-002"
        ledger = {"version": "sfdc-local-operation-ledger-v1", "entries": [{
            "request_uid": "REQ-beforetest-001",
            "operation_fingerprint": preflight["operation_fingerprint"],
            "change_intent_fingerprint": preflight["change_intent_fingerprint"],
            "state": "VERIFIED"}]}
        with self.assertRaisesRegex(ValueError, "identical change intent"):
            enforce_clean_ledger(changed, bridge(), lookups(), ledger)


class ExpectedBeforeValueContracts(unittest.TestCase):
    def test_exact_values_verify_compare_and_swap_only(self):
        result = evaluate_before(preflight(), req(),
                                 {"Amount": "100.00", "Close Date": "01/02/2099"})
        self.assertEqual(result, "VERIFIED_LIVE_BEFORE_VALUES")

    def test_different_decimal_display_is_hold(self):
        result = evaluate_before(preflight(), req(),
                                 {"Amount": "100", "Close Date": "01/02/2099"})
        self.assertEqual(result, "HOLD_LIVE_BEFORE_VALUE_CHANGED")

    def test_different_date_format_is_hold(self):
        result = evaluate_before(preflight(), req(),
                                 {"Amount": "100.00", "Close Date": "2099-01-02"})
        self.assertEqual(result, "HOLD_LIVE_BEFORE_VALUE_CHANGED")

    def test_other_user_changed_amount_is_hold(self):
        result = evaluate_before(preflight(), req(),
                                 {"Amount": "110.00", "Close Date": "01/02/2099"})
        self.assertEqual(result, "HOLD_LIVE_BEFORE_VALUE_CHANGED")

    def test_missing_field_is_hold(self):
        result = evaluate_before(preflight(), req(), {"Amount": "100.00"})
        self.assertEqual(result, "HOLD_LIVE_FIELD_SET_MISMATCH")

    def test_extra_unreviewed_field_is_hold(self):
        result = evaluate_before(preflight(), req(), {
            "Amount": "100.00", "Close Date": "01/02/2099", "Stage": "Quote Issued",
        })
        self.assertEqual(result, "HOLD_LIVE_FIELD_SET_MISMATCH")

    def test_partial_before_request_is_hold(self):
        r = req()
        del r["expected_before_values"]["Close Date"]
        self.assertEqual(evaluate_before(preflight(), r, {
            "Amount": "100.00", "Close Date": "01/02/2099",
        }), "HOLD_LIVE_FIELD_SET_MISMATCH")

    def test_preflight_cannot_allow_save(self):
        p = preflight()
        p["save_allowed"] = True
        with self.assertRaises(ValueError):
            evaluate_before(p, req(), {})

    def test_invalid_observed_object_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_before(preflight(), req(), None)


if __name__ == "__main__":
    unittest.main()
