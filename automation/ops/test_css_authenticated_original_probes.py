"""Regression: original source vs sink projection must fail closed and never certify business."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from css_authenticated_original_probes import (
    compare_feishu_projection, validate_mail_coverage, same_rows, manifest_index,
)


def mail_folders():
    return {
        "INBOX": {"folder": "INBOX", "uidvalidity": "256", "uids": ["1", "2"]},
        "SENT": {"folder": "Sent Messages", "uidvalidity": "512", "uids": ["3"]},
    }


def feishu_snapshot():
    return {
        "sheet_id": "abc", "source_date": "2026-10-31",
        "row_count": 2, "schema": "HEADER_MATCHED",
        "projected_grid": [["Project Number", "Invoice Amount"],
                           ["X1", "1000"], ["X2", "2000"]],
    }


class OriginalProbesTests(unittest.TestCase):
    def test_verified_original_uids_and_staging_are_covered_only(self):
        keys = ["INBOX|256|1", "INBOX|256|2", "Sent Messages|512|3", "OLD|1|99"]
        r = validate_mail_coverage(mail_folders(), keys)
        self.assertEqual(r["uid_coverage_state"], "PASS_UID_ONLY")
        self.assertEqual(r["missing_uid_count"], 0)
        self.assertFalse(r["mime_body_verified"])
        self.assertEqual(r["imap_uid_count"], 3)
        self.assertEqual(r["covered_uid_count"], 3)

    def test_missing_staging_uid_is_sink_lag_not_no_new_data(self):
        r = validate_mail_coverage(mail_folders(), ["INBOX|256|1"])
        self.assertEqual(r["uid_coverage_state"], "SINK_LAG")
        self.assertEqual(r["missing_uid_count"], 2)

    def test_uidvalidity_necessary_for_identity(self):
        original = mail_folders()
        original["SENT"]["uidvalidity"] = ""
        with self.assertRaisesRegex(ValueError, "UID_EVIDENCE_INVALID"):
            validate_mail_coverage(original, ["INBOX|256|1"])

    def test_source_access_missing_cannot_certify_zero(self):
        with self.assertRaisesRegex(ValueError, "FOLDER_COVERAGE_MISSING"):
            validate_mail_coverage({}, ["INBOX|256|1"])
        with self.assertRaisesRegex(ValueError, "MAIL_STAGING_NOT_READ"):
            validate_mail_coverage(mail_folders(), [])

    def test_duplicate_staging_key_blocks(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_UID_KEY"):
            validate_mail_coverage(mail_folders(), ["INBOX|256|1"] * 2)

    def test_original_feishu_full_row_projection_and_date(self):
        obj = feishu_snapshot()
        meta = {"id": "abc", "date": "2026-10-31", "rows": 2, "schema": "HEADER_MATCHED"}
        mirror = [["Project Number", "Invoice Amount"], ["X1", "1000"],
                  ["X2", "2000"]]
        r = compare_feishu_projection(obj, meta, mirror)
        self.assertEqual(r["status"], "PASS_SNAPSHOT_PROJECTION_ONLY")
        self.assertTrue(r["content_parity"])
        self.assertFalse(r["invoice_issue_dates_certified"])
        self.assertFalse(r["bank_payments_certified"])

    def test_same_row_count_but_modified_amount_is_sink_lag(self):
        obj = feishu_snapshot()
        meta = {"id": "abc", "date": "2026-10-31", "rows": 2, "schema": "HEADER_MATCHED"}
        mirror = [["Project Number", "Invoice Amount"], ["X1", "1000"],
                  ["X2", "9999"]]
        r = compare_feishu_projection(obj, meta, mirror)
        self.assertEqual(r["status"], "SINK_LAG")
        self.assertFalse(r["content_parity"])

    def test_stale_source_id_not_masked_by_recent_mirror_sync(self):
        obj = feishu_snapshot()
        meta = {"id": "def", "date": "2026-10-31", "rows": 2, "schema": "HEADER_MATCHED"}
        r = compare_feishu_projection(obj, meta, obj["projected_grid"])
        self.assertEqual(r["status"], "SINK_LAG")
        self.assertFalse(r["identity_parity"])

    def test_missing_row_detected(self):
        obj = feishu_snapshot()
        meta = {"id": "abc", "date": "2026-10-31", "rows": 2, "schema": "HEADER_MATCHED"}
        r = compare_feishu_projection(obj, meta, obj["projected_grid"][:-1])
        self.assertEqual(r["status"], "SINK_LAG")

    def test_trailing_blank_cell_in_google_trimmed_is_equivalent(self):
        self.assertTrue(same_rows([["A", "B"], ["1", ""]], [["A", "B"], ["1"]]))
        self.assertFalse(same_rows([["A", "B"]], [["A", "B", "EXTRA"]]))

    def test_manifest_requires_all_formats_and_count(self):
        manifest = [["Source", "Source Date", "Synced At KST", "Source ID", "Rows", "Schema", "Meaning"]]
        for name in ("Payment Outstanding", "Payment Receipt", "Prepayments", "eTax Invoice"):
            manifest.append([name, "2026-10-31", "now", "abc", "2", "HEADER_MATCHED", "info"])
        self.assertEqual(len(manifest_index(manifest)), 4)
        manifest[1][4] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "COUNT_INVALID"):
            manifest_index(manifest)


if __name__ == "__main__":
    unittest.main()
