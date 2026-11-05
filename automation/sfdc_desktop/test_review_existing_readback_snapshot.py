"""Pure offline readback gate regressions; all Salesforce IDs/values synthetic."""
import copy
import unittest

from capture_existing_opportunity_snapshot import PROVENANCE
from review_existing_readback_snapshot import compare, _aware_time

OPP = "006000000000000AAA"
ACCT = "001000000000000AAA"
CONTACT = "003000000000000AAA"
BUS = "Opp-2099-01-01-345678"
UID = "REQ-synthetic-readback-001"


def request():
    return {
        "request_uid": UID,
        "mode": "EXISTING_OPPORTUNITY_FILL_ONLY",
        "reviewed_current_deal_values": True,
        "target_opportunity_record_id": OPP,
        "business_opportunity_id": BUS,
        "expected_account_record_id": ACCT,
        "expected_contact_record_id": CONTACT,
        "expected_before_values": {"Amount": "100.00"},
        "changes": {"Amount": "200.00"},
        "save_allowed": False,
    }


def bridge():
    return {
        "version": "live-related-quote-report-bridge-v1",
        "status": "VERIFIED_BY_LIVE_QUOTATION_REPORT",
        "identity_verified": True,
        "opportunity_record_id": OPP,
        "business_opportunity_id": BUS,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def links():
    return {
        "account_contact_field_links_verified": True,
        "opportunity_record_id": OPP,
        "account_record_id": ACCT,
        "contact_record_id": CONTACT,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
    }


def pflight():
    from prepare_existing_change_review import prepare
    return prepare(request(), bridge(), links())


def ledger(state="READBACK_REQUIRED"):
    pre = pflight()
    return {
        "version": "sfdc-local-operation-ledger-v1",
        "entries": [{
            "request_uid": UID,
            "operation_fingerprint": pre["operation_fingerprint"],
            "change_intent_fingerprint": pre["change_intent_fingerprint"],
            "state": state,
            "updated_utc": "2099-01-01T12:00:00+00:00",
        }],
    }


def approval():
    pre = pflight()
    return {
        "approved_action": "SAVE_EXISTING_OPPORTUNITY",
        "request_uid": UID, "operation_fingerprint": pre["operation_fingerprint"],
        "approved_for_record": OPP, "explicit_current_deal_approval": True,
    }


def snapshot():
    return {
        "version": "sfdc-opportunity-reloaded-baseline-v1",
        "source": PROVENANCE,
        "page_reload_invoked": True,
        "post_save_attested": False,
        "salesforce_save_performed": False,
        "save_allowed": False,
        "captured_at_utc": "2099-01-01T12:00:01+00:00",
        "opportunity_record_id": OPP,
        "business_id_from_prior_report": BUS,
        "account_record_id": ACCT,
        "contact_record_id": CONTACT,
        "current_field_values": {
            "Opportunity Name": "Synthetic Existing Deal",
            "Amount": "200.00",
            "Close Date": "2099-02-01",
        },
    }


def evaluate(req=None, br=None, ln=None, lg=None, ap=None, sn=None):
    return compare(
        request() if req is None else req,
        bridge() if br is None else br,
        links() if ln is None else ln,
        ledger() if lg is None else lg,
        approval() if ap is None else ap,
        snapshot() if sn is None else sn,
    )


class ReadbackContentReviewTests(unittest.TestCase):
    def test_all_synthetic_values_match_but_not_save_proof(self):
        r = evaluate()
        self.assertEqual(r["status"], "READBACK_CONTENT_MATCH_REVIEW_REQUIRED")
        self.assertFalse(r["save_confirmed"])
        self.assertFalse(r["save_allowed"])
        self.assertTrue(r["human_review_required"])
        self.assertEqual(r["matched_field_count"], 1)

    def test_missing_review_holds(self):
        x = request()
        x["reviewed_current_deal_values"] = False
        self.assertEqual(evaluate(req=x)["status"], "HOLD_CHANGE_REVIEW_MISSING")

    def test_unsupported_field_holds(self):
        x = request()
        x["changes"] = {"Stage": "Closed Won"}
        x["expected_before_values"] = {"Stage": "Open"}
        self.assertEqual(evaluate(req=x)["status"], "HOLD_UNSUPPORTED_SALESFORCE_FIELDS")

    def test_no_save_event_holds(self):
        self.assertEqual(evaluate(lg=ledger("PREPARED"))["status"],
                         "HOLD_NO_EXTERNAL_SAVE_EVENT")

    def test_unknown_outcome_may_only_enter_review(self):
        x = evaluate(lg=ledger("WRITE_OUTCOME_UNKNOWN"))
        self.assertEqual(x["status"], "READBACK_CONTENT_MATCH_REVIEW_REQUIRED")
        self.assertFalse(x["save_confirmed"])

    def test_no_save_approval_holds(self):
        x = approval()
        x["approved_action"] = "FILL_ONLY"
        self.assertEqual(evaluate(ap=x)["status"], "HOLD_EXPLICIT_SAVE_APPROVAL_MISSING")

    def test_wrong_approval_target_holds(self):
        x = approval()
        x["approved_for_record"] = "006000000000001AAA"
        self.assertEqual(evaluate(ap=x)["status"], "HOLD_EXPLICIT_SAVE_APPROVAL_MISSING")

    def test_wrong_approval_fingerprint_holds(self):
        x = approval()
        x["operation_fingerprint"] = "f" * 64
        self.assertEqual(evaluate(ap=x)["status"], "HOLD_EXPLICIT_SAVE_APPROVAL_MISSING")

    def test_wrong_ledger_operation_fingerprint_holds(self):
        x = ledger()
        x["entries"][0]["operation_fingerprint"] = "e" * 64
        self.assertEqual(evaluate(lg=x)["status"], "HOLD_LEDGER_IDENTITY_MISMATCH")

    def test_wrong_ledger_intent_fingerprint_holds(self):
        x = ledger()
        x["entries"][0]["change_intent_fingerprint"] = "f" * 64
        self.assertEqual(evaluate(lg=x)["status"], "HOLD_LEDGER_IDENTITY_MISMATCH")

    def test_missing_external_operation_holds(self):
        x = {"version": "sfdc-local-operation-ledger-v1", "entries": []}
        self.assertEqual(evaluate(lg=x)["status"], "HOLD_NO_PRIOR_RECORDED_OPERATION")

    def test_snapshot_prior_to_write_event_holds(self):
        x = snapshot()
        x["captured_at_utc"] = "2099-01-01T11:00:00+00:00"
        self.assertEqual(evaluate(sn=x)["status"],
                         "HOLD_SNAPSHOT_PRECEDES_RECORDED_EXTERNAL_ACTION")

    def test_timestamp_equal_is_not_after(self):
        x = snapshot()
        x["captured_at_utc"] = "2099-01-01T12:00:00+00:00"
        self.assertEqual(evaluate(sn=x)["status"],
                         "HOLD_SNAPSHOT_PRECEDES_RECORDED_EXTERNAL_ACTION")

    def test_missing_timestamp_holds(self):
        x = snapshot()
        x.pop("captured_at_utc")
        self.assertEqual(evaluate(sn=x)["status"],
                         "HOLD_SNAPSHOT_PRECEDES_RECORDED_EXTERNAL_ACTION")

    def test_wrong_salesforce_target_holds(self):
        x = snapshot()
        x["opportunity_record_id"] = "006000000000001AAA"
        self.assertEqual(evaluate(sn=x)["status"],
                         "HOLD_RELOADED_RECORD_OR_LOOKUP_ID_MISMATCH")

    def test_wrong_account_link_holds(self):
        x = snapshot()
        x["account_record_id"] = "001000000000001AAA"
        self.assertEqual(evaluate(sn=x)["status"],
                         "HOLD_RELOADED_RECORD_OR_LOOKUP_ID_MISMATCH")

    def test_wrong_contact_link_holds(self):
        x = snapshot()
        x["contact_record_id"] = "003000000000001AAA"
        self.assertEqual(evaluate(sn=x)["status"],
                         "HOLD_RELOADED_RECORD_OR_LOOKUP_ID_MISMATCH")

    def test_different_amount_value_holds(self):
        x = snapshot()
        x["current_field_values"]["Amount"] = "100.00"
        self.assertEqual(evaluate(sn=x)["status"], "HOLD_RELOADED_CHANGE_VALUE_DIFFERENT")

    def test_different_amount_display_format_holds(self):
        x = snapshot()
        x["current_field_values"]["Amount"] = "200"
        self.assertEqual(evaluate(sn=x)["status"], "HOLD_RELOADED_CHANGE_VALUE_DIFFERENT")

    def test_fake_post_save_flag_is_not_accepted(self):
        x = snapshot()
        x["post_save_attested"] = True
        with self.assertRaises(ValueError):
            evaluate(sn=x)

    def test_malformed_ledger_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(lg={"entries": []})

    def test_timestamp_without_timezone_untrusted(self):
        self.assertIsNone(_aware_time("2099-01-01T12:00:00"))

    def test_missing_snapshot_holds(self):
        self.assertEqual(evaluate(sn={})["status"],
                         "HOLD_FRESH_UI_SNAPSHOT_MISSING")


if __name__ == "__main__":
    unittest.main()
