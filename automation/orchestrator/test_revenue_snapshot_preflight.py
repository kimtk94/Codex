"""Offline tests for read-only revenue mirror audit. No Google or Feishu API calls."""
import copy
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import revenue_snapshot_preflight as mirror
from test_monthly_revenue_canonical import source as synthetic_source

KST = mirror.KST


def source():
    data = synthetic_source()
    for row in data["BI Revenue Net VAT Monthly"]:
        if row["Month"] == "2026-11":
            row["Verified At KST"] = "2026-11-14 19:46:21 KST"
    for row in data["BI Revenue Lifecycle Monthly"]:
        row["Snapshot KST"] = "2026-11-14 19:45:59 KST"
    for row in data["Revenue Source Authority"]:
        if row["Month"] == "2026-11":
            row["Verified KST"] = "2026-11-14 19:46:24 KST"
    return data


class RevenueMirrorTests(unittest.TestCase):
    def test_three_way_consistent_but_aged_is_not_live_business_pass(self):
        r = mirror.measure(source(), month="2026-11",
                           checked_at=dt.datetime(2026, 11, 16, 21, 0, tzinfo=KST))
        self.assertEqual("MIRROR_3WAY_PARITY_AGED", r["status"])
        self.assertEqual("AGED_RECHECK", r["snapshot_age_state"])
        self.assertEqual(3, r["source_tabs_checked"])
        self.assertTrue(r["three_way_aggregate_parity"])
        self.assertFalse(r["business_source_original_probed"])
        self.assertFalse(r["feishu_base_sink_readback_probed"])
        self.assertEqual("NOT_VERIFIED", r["business_source_sink_verification"])
        self.assertNotIn("38261300", str(r))
        self.assertNotIn("34,783,000", str(r))

    def test_recent_is_still_mirror_only(self):
        r = mirror.measure(source(), month="2026-11",
                           checked_at=dt.datetime(2026, 11, 15, 1, 0, tzinfo=KST))
        self.assertEqual("MIRROR_3WAY_PARITY_RECENT", r["status"])
        self.assertEqual("NOT_VERIFIED", r["business_source_sink_verification"])

    def test_lifecycle_count_mismatch_refuses_parity(self):
        s = source()
        s["BI Revenue Lifecycle Monthly"][1]["Invoice Count"] = "5"
        with self.assertRaisesRegex(RuntimeError, "LIFECYCLE"):
            mirror.measure(s, month="2026-11",
                           checked_at=dt.datetime(2026, 11, 15, tzinfo=KST))

    def test_authority_gross_mismatch_refuses_parity(self):
        s = source()
        for row in s["Revenue Source Authority"]:
            if row["Month"] == "2026-11" and row["Source Role"] == "CANONICAL_ACTUAL_GROSS":
                row["Amount KRW"] = "0"
        with self.assertRaisesRegex(RuntimeError, "AUTHORITY"):
            mirror.measure(s, month="2026-11",
                           checked_at=dt.datetime(2026, 11, 15, tzinfo=KST))

    def test_future_or_missing_timestamps_fail_closed(self):
        s = source()
        s["BI Revenue Lifecycle Monthly"][1]["Snapshot KST"] = "2026-11-17 19:45:59 KST"
        with self.assertRaises(ValueError):
            mirror.measure(s, month="2026-11",
                           checked_at=dt.datetime(2026, 11, 16, tzinfo=KST))
        s = source()
        s["BI Revenue Lifecycle Monthly"][1].pop("Snapshot KST")
        with self.assertRaises((ValueError, TypeError)):
            mirror.measure(s, month="2026-11",
                           checked_at=dt.datetime(2026, 11, 16, tzinfo=KST))

    def test_missing_month_is_not_no_new_data(self):
        s = source()
        with self.assertRaisesRegex(ValueError, "TARGET_MONTH_NOT_CERTIFIED"):
            mirror.measure(s, month="2026-09",
                           checked_at=dt.datetime(2026, 11, 16, tzinfo=KST))

    def test_schema_duplicate_header_rejected(self):
        with self.assertRaisesRegex(ValueError, "HEADERS_INVALID"):
            mirror.rows_to_dict([["Month", "Month"], ["2026-11", "2026-11"]])
        self.assertEqual([{"Month": "2026-11"}],
                         mirror.rows_to_dict([["Month"], ["2026-11"]]))

    def test_no_credentials_cannot_be_reported_as_zero_new_invoices(self):
        with patch.dict(mirror.os.environ, {"CKD_DRIVE_SA_JSON": ""}):
            with self.assertRaisesRegex(RuntimeError, "CREDENTIALS_UNAVAILABLE"):
                mirror.mirror_source()

    def test_report_has_no_raw_amounts_and_is_explicitly_mirror_only(self):
        report = mirror.measure(source(), month="2026-11",
                                checked_at=dt.datetime(2026, 11, 16, 21, tzinfo=KST))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            mirror.write_receipt(report, out)
            text = out.read_text()
            self.assertIn("NOT_VERIFIED", text)
            self.assertNotIn("34783000", text)
            self.assertNotIn("38261300", text)

    def test_invalid_snapshot_age_threshold_rejected(self):
        with self.assertRaises(ValueError):
            mirror.measure(source(), month="2026-11",
                           checked_at=dt.datetime(2026, 11, 16, tzinfo=KST),
                           max_age_hours=0)


if __name__ == "__main__":
    unittest.main()
