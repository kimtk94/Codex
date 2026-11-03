"""Synthetic Salesforce independent reload stability tests (no live CRM)."""
import unittest
from datetime import datetime, timezone

from capture_existing_opportunity_snapshot import PROVENANCE
from verify_reloaded_snapshot_pair import verify_pair

NOW = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)


def snapshot(stamp):
    return {
        "version": "sfdc-opportunity-reloaded-baseline-v1",
        "source": PROVENANCE,
        "page_reload_invoked": True,
        "post_save_attested": False,
        "save_allowed": False,
        "salesforce_save_performed": False,
        "captured_at_utc": stamp,
        "opportunity_record_id": "006000000000000AAA",
        "business_id_from_prior_report": "Opp-2099-01-01-123456",
        "account_record_id": "001000000000000AAA",
        "contact_record_id": "003000000000000AAA",
        "current_field_values": {
            "Opportunity Name": "Synthetic Prior Deal",
            "Amount": "200.00",
            "Close Date": "2099-01-01",
        },
    }


def pair():
    return snapshot("2026-11-03T01:00:00+00:00"), snapshot("2026-11-03T02:00:00+00:00")


class TwoReloadStabilityTests(unittest.TestCase):
    def test_valid_two_reloads_not_proof_save(self):
        a, b = pair()
        r = verify_pair(a, b, NOW)
        self.assertEqual(r["status"], "TWO_RELOADED_BASELINES_MATCH_NOT_SAVE_PROOF")
        self.assertTrue(r["two_reload_baseline_consistent"])
        self.assertEqual(r["checked_field_count"], 3)
        self.assertEqual(r["seconds_between_reloads"], 3600)
        self.assertFalse(r["save_allowed"])
        self.assertFalse(r["save_confirmed"])

    def test_same_timestamp_does_not_count_as_two(self):
        a, b = pair()
        b["captured_at_utc"] = a["captured_at_utc"]
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_NOT_TWO_SEQUENTIAL_RELOADS")

    def test_reverse_time_order_blocks(self):
        a, b = pair()
        a["captured_at_utc"], b["captured_at_utc"] = b["captured_at_utc"], a["captured_at_utc"]
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_NOT_TWO_SEQUENTIAL_RELOADS")

    def test_capture_gap_over_two_hours_blocks(self):
        a, b = pair()
        a["captured_at_utc"] = "2026-11-02T22:00:00+00:00"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_STALE_OR_FUTURE_CAPTURE")

    def test_old_pair_cached_more_than_four_hours_blocks(self):
        a, b = pair()
        a["captured_at_utc"] = "2026-11-02T19:00:00+00:00"
        b["captured_at_utc"] = "2026-11-02T20:00:00+00:00"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_STALE_OR_FUTURE_CAPTURE")

    def test_future_capture_more_than_two_minutes_blocks(self):
        a, b = pair()
        a["captured_at_utc"] = "2026-11-03T04:10:00+00:00"
        b["captured_at_utc"] = "2026-11-03T04:11:00+00:00"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_STALE_OR_FUTURE_CAPTURE")

    def test_account_link_changed_blocks(self):
        a, b = pair()
        b["account_record_id"] = "001000000000001AAA"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_LOOKUP_LINK_DRIFT")

    def test_contact_link_changed_blocks(self):
        a, b = pair()
        b["contact_record_id"] = "003000000000001AAA"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_LOOKUP_LINK_DRIFT")

    def test_business_opportunity_id_changed_blocks(self):
        a, b = pair()
        b["business_id_from_prior_report"] = "Opp-2099-01-01-444444"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_DIFFERENT_CACHED_BUSINESS_ID")

    def test_amount_drift_blocks(self):
        a, b = pair()
        b["current_field_values"]["Amount"] = "250.00"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_FIELD_VALUE_DRIFT")

    def test_date_format_drift_blocks(self):
        a, b = pair()
        b["current_field_values"]["Close Date"] = "01/01/2099"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_FIELD_VALUE_DRIFT")

    def test_fake_post_save_attestation_blocks(self):
        a, b = pair()
        b["post_save_attested"] = True
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_INVALID_SNAPSHOT")

    def test_missing_reload_flag_blocks(self):
        a, b = pair()
        a["page_reload_invoked"] = False
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_INVALID_SNAPSHOT")

    def test_missing_field_blocks(self):
        a, b = pair()
        del a["current_field_values"]["Amount"]
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_INVALID_SNAPSHOT")

    def test_missing_capture_timestamp_blocks(self):
        a, b = pair()
        b.pop("captured_at_utc")
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_UNTRUSTED_CAPTURE_TIME")

    def test_naive_capture_timestamp_blocks(self):
        a, b = pair()
        b["captured_at_utc"] = "2026-11-03T02:00:00"
        self.assertEqual(verify_pair(a, b, NOW)["status"], "HOLD_UNTRUSTED_CAPTURE_TIME")

    def test_naive_comparison_clock_rejected(self):
        a, b = pair()
        with self.assertRaises(ValueError):
            verify_pair(a, b, datetime(2026, 11, 3, 4, 0))

    def test_missing_snapshot_is_hold(self):
        a, b = pair()
        self.assertEqual(verify_pair(a, {}, NOW)["status"], "HOLD_INVALID_SNAPSHOT")


if __name__ == "__main__":
    unittest.main()
