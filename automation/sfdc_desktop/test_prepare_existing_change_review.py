"""Offline synthetic tests for reviewed existing-Opportunity change requests."""
import unittest

from prepare_existing_change_review import prepare, validate_field_value

OPPORTUNITY = "006000000000000AAA"
ACCOUNT = "001000000000000AAA"
CONTACT = "003000000000000AAA"
BUSINESS = "Opp-2099-01-01-333333"


def bridge():
    return {
        "version": "live-related-quote-report-bridge-v1",
        "status": "VERIFIED_BY_LIVE_QUOTATION_REPORT",
        "identity_verified": True,
        "save_allowed": False,
        "salesforce_save_performed": False,
        "opportunity_record_id": OPPORTUNITY,
        "business_opportunity_id": BUSINESS,
    }


def lookups():
    return {
        "account_contact_field_links_verified": True,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
        "opportunity_record_id": OPPORTUNITY,
        "account_record_id": ACCOUNT,
        "contact_record_id": CONTACT,
    }


def request():
    return {
        "request_uid": "REQ-synthetic-0001",
        "mode": "EXISTING_OPPORTUNITY_FILL_ONLY",
        "reviewed_current_deal_values": True,
        "target_opportunity_record_id": OPPORTUNITY,
        "business_opportunity_id": BUSINESS,
        "expected_account_record_id": ACCOUNT,
        "expected_contact_record_id": CONTACT,
        "expected_before_values": {"Close Date": "2099-01-01", "Amount": "150"},
        "changes": {"Close Date": "2099-01-02", "Amount": "200"},
        "save_allowed": False,
    }


class OfflineRequestPreflightTests(unittest.TestCase):
    def test_valid_reviewed_request_stays_unsaved(self):
        r = prepare(request(), bridge(), lookups())
        self.assertEqual(r["status"], "PREPARED_FOR_LIVE_BEFORE_VALUE_CHECK")
        self.assertEqual(r["changed_fields"], ["Amount", "Close Date"])
        self.assertFalse(r["save_allowed"])
        self.assertFalse(r["live_before_values_verified"])
        self.assertFalse(r["salesforce_save_performed"])

    def test_idempotency_fingerprint_deterministic(self):
        a = prepare(request(), bridge(), lookups())
        b = prepare(request(), bridge(), lookups())
        self.assertEqual(a["operation_fingerprint"], b["operation_fingerprint"])

    def test_duplicate_uid_refused(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            prepare(request(), bridge(), lookups(), ["REQ-synthetic-0001"])

    def test_missing_human_review_flag_refused(self):
        x = request()
        x["reviewed_current_deal_values"] = False
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_wrong_opportunity_refused(self):
        x = request()
        x["target_opportunity_record_id"] = "006000000000001AAA"
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_wrong_business_id_refused(self):
        x = request()
        x["business_opportunity_id"] = "Opp-2099-01-01-000001"
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_wrong_account_id_refused(self):
        x = request()
        x["expected_account_record_id"] = "001000000000001AAA"
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_wrong_contact_id_refused(self):
        x = request()
        x["expected_contact_record_id"] = "003000000000001AAA"
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_editing_lookup_by_name_forbidden(self):
        x = request()
        x["changes"] = {"Account Name": "similar name"}
        x["expected_before_values"] = {"Account Name": "original"}
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_stage_mutation_not_yet_authorized(self):
        x = request()
        x["changes"] = {"Stage": "Closed Won"}
        x["expected_before_values"] = {"Stage": "Quote Issued"}
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_missing_before_value_refused(self):
        x = request()
        del x["expected_before_values"]["Amount"]
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_unmodified_field_should_use_noop_audit(self):
        x = request()
        x["changes"]["Amount"] = "150"
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_request_must_explicitly_prohibit_save(self):
        x = request()
        x["save_allowed"] = True
        with self.assertRaises(ValueError):
            prepare(x, bridge(), lookups())

    def test_invalid_amounts_rejected(self):
        for value in ("₩2,000", "KRW 100", "-1", "1e9", "1.999", "NaN", "Infinity", " 12"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_field_value("Amount", value)

    def test_valid_amounts(self):
        for value in ("0", "100", "100.50", "999999999999.99"):
            with self.subTest(value=value):
                self.assertEqual(validate_field_value("Amount", value), value)

    def test_close_date_reject_invalid(self):
        for value in ("2099/01/01", "2099-02-30", "01/01/2099", "2099-13-01"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_field_value("Close Date", value)

    def test_no_empty_field_value(self):
        with self.assertRaises(ValueError):
            validate_field_value("Opportunity Name", "")

    def test_description_length_gate(self):
        with self.assertRaises(ValueError):
            validate_field_value("Progress Description", "a" * 1501)


if __name__ == "__main__":
    unittest.main()
