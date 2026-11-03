"""Synthetic tests for fresh reloaded Salesforce baseline; no CRM access."""
import copy
import unittest
from unittest.mock import patch

from capture_existing_opportunity_snapshot import (
    PROVENANCE, validate_snapshot, compare_snapshots, preflight, snapshot_browser,
)

OPP = "006000000000000AAA"
ACCOUNT = "001000000000000AAA"
CONTACT = "003000000000000AAA"
BUSINESS = "Opp-2099-01-01-123456"


def snapshot():
    return {
        "version": "sfdc-opportunity-reloaded-baseline-v1",
        "source": PROVENANCE,
        "page_reload_invoked": True,
        "post_save_attested": False,
        "save_allowed": False,
        "salesforce_save_performed": False,
        "business_id_from_prior_report": BUSINESS,
        "business_id_freshly_reconfirmed_from_report": False,
        "opportunity_record_id": OPP,
        "account_record_id": ACCOUNT,
        "contact_record_id": CONTACT,
        "current_field_values": {
            "Opportunity Name": "Synthetic Original",
            "Amount": "150.00",
            "Close Date": "2099-01-02",
        },
    }


def bridge():
    return {
        "version": "live-related-quote-report-bridge-v1",
        "status": "VERIFIED_BY_LIVE_QUOTATION_REPORT",
        "identity_verified": True,
        "opportunity_record_id": OPP,
        "business_opportunity_id": BUSINESS,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def links():
    return {
        "account_contact_field_links_verified": True,
        "opportunity_record_id": OPP,
        "account_record_id": ACCOUNT,
        "contact_record_id": CONTACT,
        "salesforce_save_allowed": False,
        "salesforce_save_performed": False,
    }


class ReadOnlySnapshotContractTests(unittest.TestCase):
    def test_valid_snapshot_does_not_certify_save(self):
        s = snapshot()
        self.assertTrue(validate_snapshot(s))
        self.assertFalse(s["post_save_attested"])
        self.assertFalse(s["save_allowed"])

    def test_valid_prior_evidence(self):
        self.assertTrue(preflight(bridge(), links()))

    def test_missing_bridge_identity_blocks(self):
        b = bridge()
        b["identity_verified"] = False
        with self.assertRaises(ValueError):
            preflight(b, links())

    def test_cross_opportunity_links_block(self):
        l = links()
        l["opportunity_record_id"] = "006000000000001AAA"
        with self.assertRaises(ValueError):
            preflight(bridge(), l)

    def test_invalid_cached_business_id_blocks(self):
        s = snapshot()
        s["business_id_from_prior_report"] = "006000000000000AAA"
        with self.assertRaises(ValueError):
            validate_snapshot(s)

    def test_fake_post_save_attestation_blocks_baseline(self):
        s = snapshot()
        s["post_save_attested"] = True
        with self.assertRaises(ValueError):
            validate_snapshot(s)

    def test_fake_source_blocks(self):
        s = snapshot()
        s["source"] = "Salesforce UI after explicit Save and page reload"
        with self.assertRaises(ValueError):
            validate_snapshot(s)

    def test_missing_reload_blocks(self):
        s = snapshot()
        s["page_reload_invoked"] = False
        with self.assertRaises(ValueError):
            validate_snapshot(s)

    def test_missing_one_of_three_fields_blocks(self):
        s = snapshot()
        del s["current_field_values"]["Close Date"]
        with self.assertRaises(ValueError):
            validate_snapshot(s)

    def test_malformed_contact_record_blocks(self):
        s = snapshot()
        s["contact_record_id"] = "001000000000000AAA"
        with self.assertRaises(ValueError):
            validate_snapshot(s)

    def test_matching_snapshots_do_not_prove_save(self):
        self.assertEqual(compare_snapshots(snapshot(), snapshot()),
                         "SNAPSHOTS_MATCH_NOT_PROOF_OF_SAVE")

    def test_amount_drift_detected(self):
        before, after = snapshot(), snapshot()
        after["current_field_values"]["Amount"] = "160.00"
        self.assertEqual(compare_snapshots(before, after), "HOLD_FIELD_VALUE_DRIFT")

    def test_date_format_drift_detected(self):
        before, after = snapshot(), snapshot()
        after["current_field_values"]["Close Date"] = "01/02/2099"
        self.assertEqual(compare_snapshots(before, after), "HOLD_FIELD_VALUE_DRIFT")

    def test_account_drift_detected(self):
        before, after = snapshot(), snapshot()
        after["account_record_id"] = "001000000000001AAA"
        self.assertEqual(compare_snapshots(before, after), "HOLD_LOOKUP_LINK_DRIFT")

    def test_contact_drift_detected(self):
        before, after = snapshot(), snapshot()
        after["contact_record_id"] = "003000000000001AAA"
        self.assertEqual(compare_snapshots(before, after), "HOLD_LOOKUP_LINK_DRIFT")

    def test_wrong_opportunity_detected(self):
        before, after = snapshot(), snapshot()
        after["opportunity_record_id"] = "006000000000001AAA"
        self.assertEqual(compare_snapshots(before, after), "HOLD_DIFFERENT_OPPORTUNITY_RECORD")

    def test_wrong_business_id_detected(self):
        before, after = snapshot(), snapshot()
        after["business_id_from_prior_report"] = "Opp-2099-01-01-654321"
        self.assertEqual(compare_snapshots(before, after), "HOLD_DIFFERENT_CACHED_BUSINESS_ID")

    def test_no_reloading_allowed_requires_error_before_using_browser(self):
        # Prevent an accidental stale-page capture shortcut.
        with self.assertRaises(ValueError):
            snapshot_browser(object(), bridge(), links(), reload_page=False)


if __name__ == "__main__":
    unittest.main()
