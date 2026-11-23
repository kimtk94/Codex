"""Regression: original source vs sink projection must fail closed and never certify business."""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from css_authenticated_original_probes import (
    compare_feishu_projection, validate_mail_coverage, same_rows, manifest_index,
    latest_ingest_checkpoint, parse_internaldate, missing_arrival_buckets,
    sanitized_gap_counts,
)


def mail_folders():
    return {
        "INBOX": {"folder": "INBOX", "uidvalidity": "256", "uids": ["1", "2"],
                  "recent_uids": ["2"], "scan_uids": ["1", "2"], "year_uids": ["1", "2"]},
        "SENT": {"folder": "Sent Messages", "uidvalidity": "512", "uids": ["3"],
                 "recent_uids": ["3"], "scan_uids": ["3"], "year_uids": ["3"]},
    }


def feishu_snapshot():
    return {
        "sheet_id": "abc", "source_date": "2026-10-31",
        "row_count": 2, "schema": "HEADER_MATCHED",
        "projected_grid": [["Project Number", "Invoice Amount"],
                           ["X1", "1000"], ["X2", "2000"]],
    }


class OriginalProbesTests(unittest.TestCase):
    def test_operational_gap_summary_is_aggregate_only(self):
        secret = "PRIVATE_CUSTOMER_ABC"
        mail = {
            "scan_365d_missing_uid_count": 14,
            "historical_61_to_365d_uid_gap": 7,
            "historical_outside_365d_uid_gap": 123,
            "customer_email": secret,
        }
        feishu = {
            "formats": {
                "Payment Outstanding": {
                    "content_different_cell_count": 3,
                    "source_customer": secret,
                },
                "eTax Invoice": {"content_different_cell_count": 0},
                "Unknown Private Tab": {"content_different_cell_count": 999},
            }
        }
        result = sanitized_gap_counts(mail, feishu)
        self.assertEqual(result["qq_missing_365d"], 14)
        self.assertEqual(result["qq_missing_61_to_365d"], 7)
        self.assertEqual(result["qq_missing_older_than_365d"], 123)
        self.assertEqual(result["feishu_changed_cells_by_format"]["Payment Outstanding"], 3)
        self.assertIsNone(result["feishu_changed_cells_by_format"]["Payment Receipt"])
        self.assertEqual(result["feishu_changed_cells_by_format"]["eTax Invoice"], 0)
        self.assertNotIn(secret, str(result))
        self.assertNotIn("Unknown Private Tab", str(result))

    def test_operational_gap_summary_unknown_is_not_zero(self):
        result = sanitized_gap_counts({"status": "SOURCE_UNAVAILABLE"},
                                      {"status": "SOURCE_UNAVAILABLE"})
        self.assertIsNone(result["qq_missing_365d"])
        self.assertIsNone(result["qq_missing_61_to_365d"])
        self.assertIsNone(result["qq_missing_older_than_365d"])
        self.assertTrue(all(value is None for value in
                            result["feishu_changed_cells_by_format"].values()))
        bad = sanitized_gap_counts({"scan_365d_missing_uid_count": True,
                                    "historical_61_to_365d_uid_gap": -1},
                                   {"formats": {"eTax Invoice": {
                                       "content_different_cell_count": "0"}}})
        self.assertIsNone(bad["qq_missing_365d"])
        self.assertIsNone(bad["qq_missing_61_to_365d"])
        self.assertIsNone(bad["feishu_changed_cells_by_format"]["eTax Invoice"])

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
        self.assertEqual(r["uid_coverage_state"], "HISTORICAL_SINK_LAG")
        self.assertEqual(r["recent_3d_state"], "SINK_LAG")
        self.assertEqual(r["recent_3d_missing_uid_count"], 2)
        self.assertEqual(r["missing_uid_count"], 2)

    def test_historical_missing_does_not_imply_current_three_day_lag(self):
        folders = mail_folders()
        folders["INBOX"]["scan_uids"] = ["2"]
        result = validate_mail_coverage(folders, [
            "INBOX|256|2", "Sent Messages|512|3",
        ])
        self.assertEqual(result["missing_uid_count"], 1)
        self.assertEqual(result["recent_3d_missing_uid_count"], 0)
        self.assertEqual(result["scan_60d_missing_uid_count"], 0)
        self.assertEqual(result["historical_outside_60d_uid_gap"], 1)
        self.assertEqual(result["recent_3d_state"], "PASS_UID_ONLY")
        self.assertEqual(result["scan_60d_state"], "PASS_UID_ONLY")
        self.assertEqual(result["uid_coverage_state"], "HISTORICAL_SINK_LAG")

    def test_one_year_priority_is_separate_from_full_mailbox_history(self):
        folders=mail_folders()
        folders["INBOX"]["uids"]=["1","2","99"]
        # Only one old UID is absent. 1 is between 61 and 365 days,
        # while 99 is older than 365 days and excluded from current review.
        folders["INBOX"]["scan_uids"]=["2"]
        folders["INBOX"]["year_uids"]=["1","2"]
        result=validate_mail_coverage(folders,["INBOX|256|2","Sent Messages|512|3"])
        self.assertEqual(2,result["missing_uid_count"])
        self.assertEqual(0,result["recent_3d_missing_uid_count"])
        self.assertEqual(0,result["scan_60d_missing_uid_count"])
        self.assertEqual(1,result["scan_365d_missing_uid_count"])
        self.assertEqual("SINK_LAG",result["scan_365d_state"])
        self.assertEqual(1,result["historical_61_to_365d_uid_gap"])
        self.assertEqual(1,result["historical_outside_365d_uid_gap"])
        self.assertEqual("IMAP_INTERNALDATE_DAY_GRAIN_ROLLING_365D",result["window_scope"])
        self.assertFalse(result["mime_body_verified"])

    def test_365d_window_requires_all_folders_and_hierarchy(self):
        folders=mail_folders()
        del folders["SENT"]["year_uids"]
        with self.assertRaisesRegex(ValueError,"WINDOW_EVIDENCE_MISSING"):
            validate_mail_coverage(folders,["INBOX|256|2"])
        folders=mail_folders()
        folders["INBOX"]["year_uids"]=["2"]
        with self.assertRaisesRegex(ValueError,"WINDOW_HIERARCHY_INVALID"):
            validate_mail_coverage(folders,["INBOX|256|2"])
        folders=mail_folders()
        folders["INBOX"]["year_uids"]=["1","2","999"]
        with self.assertRaisesRegex(ValueError,"WINDOW_NOT_SUBSET_OF_ALL"):
            validate_mail_coverage(folders,["INBOX|256|2"])

    def test_year_uid_parity_not_claimed_for_older_history(self):
        folders=mail_folders()
        folders["INBOX"]["uids"]=["1","2","99"]
        folders["INBOX"]["recent_uids"]=["2"]
        folders["INBOX"]["scan_uids"]=["2"]
        folders["INBOX"]["year_uids"]=["2"]
        result=validate_mail_coverage(folders,["INBOX|256|2","Sent Messages|512|3"])
        self.assertEqual("PASS_UID_ONLY",result["scan_365d_state"])
        self.assertEqual(2,result["historical_outside_365d_uid_gap"])
        self.assertEqual("HISTORICAL_SINK_LAG",result["uid_coverage_state"])

    def test_window_search_must_succeed_not_implicitly_zero(self):
        folders = mail_folders()
        del folders["INBOX"]["recent_uids"]
        with self.assertRaisesRegex(ValueError, "WINDOW_EVIDENCE_MISSING"):
            validate_mail_coverage(folders, ["INBOX|256|2"])

    def test_recent_window_cannot_contain_uid_not_in_all_source(self):
        folders = mail_folders()
        folders["INBOX"]["recent_uids"].append("999")
        with self.assertRaisesRegex(ValueError, "WINDOW_NOT_SUBSET_OF_ALL"):
            validate_mail_coverage(folders, ["INBOX|256|2"])

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

    def test_latest_ingest_checkpoint_uses_actual_fetched_at_not_mail_received_date(self):
        rows = [["fetched_at_utc"], ["2026-11-08T22:00:00Z"],
                ["2026-11-08T22:23:40.014311+00:00"]]
        t = latest_ingest_checkpoint(rows)
        self.assertEqual(t.isoformat(), "2026-11-08T22:23:40.014311+00:00")

    def test_bad_checkpoint_does_not_become_no_new_data(self):
        with self.assertRaisesRegex(ValueError, "TIMESTAMP_SCHEMA_INVALID"):
            latest_ingest_checkpoint([["received_at"]])
        with self.assertRaisesRegex(ValueError, "TIMESTAMP_NAIVE"):
            latest_ingest_checkpoint([["fetched_at_utc"], ["2026-11-08T22:00:00"]])

    def test_missing_internaldate_parsing_without_subject_or_body(self):
        stamp = parse_internaldate([b'42 (UID 123 INTERNALDATE "09-Nov-2026 07:50:12 +0900")'])
        self.assertEqual(stamp.isoformat(), "2026-11-08T22:50:12+00:00")
        with self.assertRaisesRegex(ValueError, "INTERNALDATE_MISSING"):
            parse_internaldate([b'42 (UID 123 RFC822.SIZE 123)'])

    def test_six_new_arrivals_after_last_ingest_not_prior_sink_lag(self):
        base = dt.datetime(2026, 11, 8, 22, 23, tzinfo=dt.timezone.utc)
        times = [base + dt.timedelta(minutes=25 + i) for i in range(6)]
        r = missing_arrival_buckets(times, base)
        self.assertEqual(r, {"before_last_ingest": 0, "after_last_ingest": 6,
                             "near_ingest_boundary": 0})

    def test_missing_uid_before_last_ingest_is_real_prior_gap(self):
        base = dt.datetime(2026, 11, 8, 22, 23, tzinfo=dt.timezone.utc)
        arrivals = [base - dt.timedelta(minutes=40), base + dt.timedelta(minutes=10),
                    base + dt.timedelta(seconds=30)]
        r = missing_arrival_buckets(arrivals, base)
        self.assertEqual(r, {"before_last_ingest": 1, "after_last_ingest": 1,
                             "near_ingest_boundary": 1})

    def test_naive_arrival_time_blocks(self):
        base = dt.datetime(2026, 11, 8, 22, 23, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(ValueError, "ARRIVAL_TIME_UNVERIFIED"):
            missing_arrival_buckets([dt.datetime(2026, 11, 8, 22, 23)], base)

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

    def test_aggregate_outstanding_drift_without_exposing_customer_cells(self):
        source = feishu_snapshot()
        source["projected_grid"][2] = ["PERSONAL_RECORD_ID", "2000"]
        meta = {"id": "abc", "date": "2026-10-31",
                "rows": 2, "schema": "HEADER_MATCHED"}
        mirror = [["Project Number", "Invoice Amount"], ["X1", "1000"],
                  ["PERSONAL_RECORD_ID", "3456"]]
        r = compare_feishu_projection(source, meta, mirror)
        self.assertEqual("SINK_LAG", r["status"])
        self.assertEqual(1, r["content_different_row_count"])
        self.assertEqual(1, r["content_different_cell_count"])
        self.assertEqual(1, r["content_different_column_count"])
        self.assertEqual(1, r["changed_nonempty_cell_count"])
        self.assertEqual(0, r["source_nonempty_mirror_empty_cell_count"])
        self.assertNotIn("PERSONAL_RECORD_ID", str(r))
        self.assertNotIn("3456", str(r))

    def test_blank_vs_missing_and_trailing_empty_equivalent(self):
        src = feishu_snapshot()
        meta = {"id": "abc", "date": "2026-10-31",
                "rows": 2, "schema": "HEADER_MATCHED"}
        src["projected_grid"] = [["A", "B"], ["PRIVATE", ""], ["Y", "Z"]]
        mirror = [["A", "B"], ["PRIVATE"], ["Y", "Z"]]
        r = compare_feishu_projection(src, meta, mirror)
        self.assertEqual("PASS_SNAPSHOT_PROJECTION_ONLY", r["status"])
        self.assertEqual(0, r["content_different_cell_count"])
        mirror = [["A", "B"], ["PRIVATE", "SINK_EXTRA"], ["Y", ""]]
        r = compare_feishu_projection(src, meta, mirror)
        self.assertEqual("SINK_LAG", r["status"])
        self.assertEqual(2, r["content_different_cell_count"])
        self.assertEqual(2, r["content_different_row_count"])
        self.assertEqual(1, r["mirror_nonempty_source_empty_cell_count"])
        self.assertEqual(1, r["source_nonempty_mirror_empty_cell_count"])
        self.assertNotIn("PRIVATE", str(r))
        self.assertNotIn("SINK_EXTRA", str(r))

    def test_absent_mirror_row_has_aggregate_gap_not_row_identity(self):
        src = feishu_snapshot()
        meta = {"id": "abc", "date": "2026-10-31",
                "rows": 2, "schema": "HEADER_MATCHED"}
        mirror = src["projected_grid"][:-1]
        r = compare_feishu_projection(src, meta, mirror)
        self.assertEqual("SINK_LAG", r["status"])
        self.assertEqual(1, r["missing_mirror_row_count"])
        self.assertEqual(0, r["unexpected_mirror_row_count"])
        self.assertEqual(1, r["content_different_row_count"])
        self.assertEqual(2, r["content_different_cell_count"])
        self.assertNotIn("X2", str(r))

    def test_safe_field_roles_and_value_shape_classify_only_aggregates(self):
        source = {
            "sheet_id": "s", "source_date": "2026-11-11",
            "row_count": 3, "schema": "HEADER_MATCHED",
            "projected_grid": [
                ["Invoice Number", "Outstanding Amount", "Status", "Note"],
                ["PRIVATE_A", "1,000", "Ready", "Memo"],
                ["PRIVATE_B", "2,500", "Open", "KEEP"],
                ["PRIVATE_C", "3,000", "Open", "KEEP"],
            ],
        }
        mirror = [
            ["Invoice Number", "Outstanding Amount", "Status", "Note"],
            ["PRIVATE_A", "1000", "Ready", "Memo"],
            ["PRIVATE_B", "2,500", "", "KEEP"],
            ["PRIVATE_C", "3,000", "Open", "KEEP "],
        ]
        meta = {"id": "s", "date": "2026-11-11",
                "rows": 3, "schema": "HEADER_MATCHED"}
        result = compare_feishu_projection(source, meta, mirror)
        self.assertEqual("SINK_LAG", result["status"])
        self.assertEqual(3, result["content_different_cell_count"])
        self.assertEqual(3, result["content_different_row_count"])
        self.assertEqual(3, result["content_different_column_count"])
        types = result["drift_characteristics"]
        self.assertEqual(1, types["NUMERIC_DISPLAY_ONLY"])
        self.assertEqual(1, types["SOURCE_FILLED_MIRROR_EMPTY"])
        self.assertEqual(1, types["WHITESPACE_ONLY"])
        self.assertEqual(0, types["SUBSTANTIVE_NONEMPTY_CHANGE"])
        roles = result["drift_business_field_roles"]
        self.assertEqual(1, roles["FINANCIAL_FIELD"])
        self.assertEqual(1, roles["STATUS_FIELD"])
        self.assertEqual(1, roles["NOTE_FIELD"])
        for secret in ("PRIVATE_A", "PRIVATE_B", "PRIVATE_C", "1,000",
                       "Invoice Number", "Outstanding Amount", "KEEP"):
            self.assertNotIn(secret, str(result))

    def test_safe_drift_classifies_substantive_change_not_numerically_equivalent(self):
        source = feishu_snapshot()
        meta = {"id":"abc", "date":"2026-10-31",
                "rows":2,"schema":"HEADER_MATCHED"}
        mirror = [["Project Number", "Invoice Amount"], ["X1","1,200 USD"],
                  ["X2", "3,000"]]
        result = compare_feishu_projection(source,meta,mirror)
        self.assertEqual(2,result["drift_characteristics"]["SUBSTANTIVE_NONEMPTY_CHANGE"])
        self.assertEqual(0,result["drift_characteristics"]["NUMERIC_DISPLAY_ONLY"])
        self.assertEqual(2,result["drift_business_field_roles"]["FINANCIAL_FIELD"])
        self.assertNotIn("3,000",str(result))

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
