#!/usr/bin/env python3
import unittest
from unittest import mock

import project_revenue_readonly_parity as parity
from project_lifecycle_refresh import HEAD
from qq_mail_ingest import SafeError


class ReadonlyParityTests(unittest.TestCase):
    def test_issued_qq_only_lifecycle_receives_existing_prior_rows(self):
        previous = [HEAD, ["X_EXISTING"]]
        def build_with_context(*source, previous_rows=None):
            if previous_rows is None:
                raise AssertionError("Previous lifecycle record context dropped")
            return [HEAD, ["X_EXISTING"]]
        with mock.patch.object(parity, "build", build_with_context):
            result = parity.compute_lifecycle([[]] * 6, previous)
        self.assertEqual(parity.project_counts(result, previous)["SINK_ONLY"], 0)

    def test_main_legacy_build_does_not_require_new_parameter(self):
        def build_without_context(*source):
            return [HEAD, ["X_EXISTING"]]
        with mock.patch.object(parity, "build", build_without_context):
            result = parity.compute_lifecycle([[]] * 6, [HEAD, ["X_EXISTING"]])
        self.assertEqual(len(result), 2)

    def test_project_set_exact_match_and_order_independent(self):
        new = [HEAD, ["X1"], ["X2"]]
        old = [HEAD[:22], ["X2"], ["X1"]]
        state = parity.project_counts(new, old)
        self.assertEqual(state["SOURCE_PROJECTS"], 2)
        self.assertEqual(state["SINK_ONLY"], 0)
        self.assertEqual(state["SOURCE_ONLY"], 0)

    def test_project_set_111_to_110_reports_loss_not_pass(self):
        new = [HEAD] + [["X" + str(i)] for i in range(110)]
        old = [HEAD] + [["X" + str(i)] for i in range(111)]
        state = parity.project_counts(new, old)
        self.assertEqual(state["SOURCE_PROJECTS"], 110)
        self.assertEqual(state["SINK_PROJECTS"], 111)
        self.assertEqual(state["SINK_ONLY"], 1)

    def test_project_duplicate_or_wrong_sink_schema_fails(self):
        with self.assertRaisesRegex(SafeError, "DUPLICATE_OR_BLANK"):
            parity.project_counts([HEAD, ["X1"], ["X1"]], [HEAD, ["X1"]])
        with self.assertRaisesRegex(SafeError, "SINK_HEADER"):
            parity.project_counts([HEAD, ["X1"]], [["Wrong"], ["X1"]])

    def test_project_issued_and_status_value_mismatch_detected(self):
        original = [""] * len(HEAD)
        original[0] = "X100"
        original[5] = "Sample received"
        original[7] = 40
        original[14] = 1
        original[15] = 1100000
        sink = list(original)
        sink[5] = "Sequencing"
        sink[7] = "40.0"
        sink[15] = "1000000"
        got = parity.project_value_counts([HEAD, original], [HEAD, sink])
        self.assertEqual(got["STATUS_MISMATCHED_PROJECTS"], 1)
        self.assertEqual(got["FINANCE_MISMATCHED_PROJECTS"], 1)

    def test_project_numeric_formats_are_equivalent(self):
        original = [""] * len(HEAD)
        original[0] = "X101"
        original[7] = 90
        original[15] = 1000000
        sink = list(original)
        sink[7] = "90.0"
        sink[15] = "1,000,000.00"
        got = parity.project_value_counts([HEAD, original], [HEAD, sink])
        self.assertEqual(got["STATUS_MISMATCHED_PROJECTS"], 0)
        self.assertEqual(got["FINANCE_MISMATCHED_PROJECTS"], 0)

    def test_project_field_counts_only_labels_and_counts(self):
        row = [""] * len(HEAD)
        row[0] = "X_ABC"
        row[5] = "Sample Received"
        row[15] = 1100000
        sink = list(row)
        sink[5] = "Sequencing"
        sink[15] = 1000000
        summary = parity.project_field_differences([HEAD, row], [HEAD, sink])
        self.assertEqual(summary["FEISHU_STATUS"], 1)
        self.assertEqual(summary["ISSUED_AMOUNT_KRW"], 1)
        self.assertEqual(summary["CSS_STAGE"], 0)
        self.assertNotIn("X_ABC", str(summary))

    def test_date_triage_identifies_format_only_not_schedule_change(self):
        self.assertEqual(parity.date_review_status("2026-11-17", "2026/11/17"), "FORMAT_ONLY")
        self.assertEqual(parity.date_review_status("2026-11-17", "2026-11-18"),
                         "DIFFERENT_CALENDAR_DAY")
        self.assertEqual(parity.date_review_status("2026-11-17", ""), "SINK_BLANK")
        self.assertEqual(parity.date_review_status("", "2026-11-17"), "SOURCE_BLANK")
        self.assertEqual(parity.date_review_status("TBD", "2026-11-17"), "UNPARSEABLE")
        self.assertEqual(parity.date_review_status("2026-11-17", "2026-11-17"), "RAW_EQUAL")

    def test_date_serial_and_offset_are_calendar_day_normalized(self):
        import datetime as dt
        origin = dt.date(1899, 12, 30)
        day = dt.date(2026, 11, 17)
        serial = str((day - origin).days)
        self.assertEqual(parity.date_review_status("2026-11-17", serial), "FORMAT_ONLY")
        self.assertEqual(parity.date_review_status("2026-11-17",
                                                   "2026-11-16T15:00:00Z"), "FORMAT_ONLY")
        self.assertEqual(parity.date_review_status("2026-11-17",
                                                   "2026-11-17 00:00:00"), "FORMAT_ONLY")

    def test_date_unclear_formats_stay_unverified(self):
        self.assertIsNone(parity.parse_expected_day("17/11/2026"))
        self.assertIsNone(parity.parse_expected_day("2026-13-20"))
        self.assertEqual(parity.date_review_status("2026-11-17", "17/11/2026"),
                         "UNPARSEABLE")

    def test_billing_transition_categorized_not_customer_exposed(self):
        a = [""] * len(HEAD)
        b = [""] * len(HEAD)
        a[0] = b[0] = "X_DO_NOT_LOG"
        a[11] = "2026-11-17"
        b[11] = "2026/11/17"
        a[16] = "ISSUED (BALANCE UNVERIFIED) [QQ_ONLY]"
        b[16] = "STATEMENT READY - INVOICE PENDING [QQ_ONLY]"
        a[14], b[14] = 1, 0
        a[15], b[15] = 1000000, 0
        a[22], b[22] = "", 1000000
        dates, bills, fin = parity.project_semantic_triage([HEAD, a], [HEAD, b])
        self.assertEqual(dates["FORMAT_ONLY"], 1)
        self.assertEqual(bills["STATEMENT_PENDING_TO_ISSUED_UNVERIFIED"], 1)
        self.assertEqual(fin["INVOICE_COUNT_UP"], 1)
        self.assertEqual(fin["ISSUED_AMOUNT_UP"], 1)
        self.assertEqual(fin["VERIFIED_PENDING_SOURCE_EMPTY"], 1)
        self.assertNotIn("X_DO_NOT_LOG", str((dates, bills, fin)))
        self.assertNotIn("1000000", str((dates, bills, fin)))

    def test_unknown_billing_category_not_false_issued(self):
        self.assertEqual(parity.billing_category("Something unexpected"), "UNKNOWN")
        self.assertEqual(parity.billing_category(""), "BLANK")

    def test_date_shift_direction_bands_and_override_origin(self):
        later = [""] * len(HEAD)
        earlier = [""] * len(HEAD)
        later[0], earlier[0] = "X_A", "X_B"
        later[11], earlier[11] = "2026-11-20", "2026-11-10"
        old_later = list(later)
        old_earlier = list(earlier)
        old_later[11], old_earlier[11] = "2026-11-19", "2026-11-20"
        controls = [["Sub-Project Number"]] + [["X_A", "", "", "", "", "", "2026-11-20"]]
        stats = parity.project_date_shift_triage(
            [HEAD, later, earlier], [HEAD, old_later, old_earlier], controls)
        self.assertEqual(stats["DATE_SHIFTS_TOTAL"], 2)
        self.assertEqual(stats["EXPECTED_LATER_1D"], 1)
        self.assertEqual(stats["EXPECTED_EARLIER_8_TO_30D"], 1)
        self.assertEqual(stats["ORIGIN_MONTH_CONTROL"], 1)
        self.assertEqual(stats["ORIGIN_FEISHU_FORECAST"], 1)
        self.assertNotIn("X_A", str(stats))
        self.assertNotIn("2026-11-20", str(stats))

    def test_feishu_alignment_splits_saved_forecast_vs_control_override(self):
        updated = [""] * len(HEAD)
        old = [""] * len(HEAD)
        updated[0] = old[0] = "X_PRIVATE"
        updated[11], old[11] = "2026-11-20", "2026-11-15"
        controls = [["Sub-Project Number", "", "", "", "", "", "Expected Completion"]]
        feishu = [["Snapshot KST"], ["", "X_PRIVATE", "", "", "", "", "", "", "", "", "", "2026-11-15"]]
        found = parity.project_control_vs_feishu_alignment(
            [HEAD, updated], [HEAD, old], controls, feishu)
        self.assertEqual(found["SINK_MATCHES_FEISHU_FORECAST"], 1)
        self.assertEqual(found["CONTROL_HEADER_TYPE_EXPECTED_COMPLETION_FIELD"], 1)
        self.assertNotIn("X_PRIVATE", str(found))
        self.assertNotIn("2026-11-15", str(found))

    def test_feishu_alignment_reports_unmatched_dates_without_guessing(self):
        updated = [""] * len(HEAD)
        old = [""] * len(HEAD)
        updated[0] = old[0] = "X_PRIVATE"
        updated[11], old[11] = "2026-11-20", "2026-11-15"
        feishu = [["Snapshot KST"], ["", "X_PRIVATE", "", "", "", "", "", "", "", "", "", "2026-11-18"]]
        controls = [["Sub-Project Number", "", "", "", "", "", "Manual Override"]]
        found = parity.project_control_vs_feishu_alignment(
            [HEAD, updated], [HEAD, old], controls, feishu)
        self.assertEqual(found["SINK_AND_CONTROL_BOTH_DIFFER_FROM_FEISHU"], 1)
        self.assertEqual(found["CONTROL_HEADER_TYPE_MANUAL_OR_OVERRIDE"], 1)

    def test_feishu_alignment_duplicate_x_or_missing_header_fails_closed(self):
        updated = [""] * len(HEAD)
        updated[0] = "X_PRIVATE"
        updated[11] = "2026-11-20"
        old = list(updated)
        old[11] = "2026-11-15"
        controls = [["Sub-Project Number", "", "", "", "", "", "Expected Completion"]]
        feishu = [["Snapshot KST"], ["", "X_PRIVATE"], ["", "X_PRIVATE"]]
        with self.assertRaisesRegex(SafeError, "FEISHU_DUPLICATE_SUBPROJECT"):
            parity.project_control_vs_feishu_alignment(
                [HEAD, updated], [HEAD, old], controls, feishu)
        with self.assertRaisesRegex(SafeError, "CONTROL_DATE_HEADER_MISSING"):
            parity.project_control_vs_feishu_alignment(
                [HEAD, updated], [HEAD, old], [["Sub-Project Number"]], feishu)

    def test_project_old_partial_header_not_false_field_pass(self):
        with self.assertRaisesRegex(SafeError, "FULL_SCHEMA_REQUIRED"):
            parity.project_value_counts([HEAD, ["X1"]], [HEAD[:22], ["X1"]])

    def test_month_equal_and_extra_historical_preserved(self):
        desired = [{"Source Key": "INVOICE:2026-11", "Invoice Count": 7}]
        existing = [
            {"record_id": "new", "fields": dict(desired[0])},
            {"record_id": "old", "fields": {"Source Key": "INVOICE:2026-09",
                                         "Invoice Count": 8}},
        ]
        stats = parity.month_counts(desired, existing)
        self.assertEqual(stats["MISSING_CANONICAL_MONTHS"], 0)
        self.assertEqual(stats["DIFFERING_CANONICAL_MONTHS"], 0)
        self.assertEqual(stats["PRESERVED_OTHER_MONTHS"], 1)

    def test_month_missing_and_wrong_amount_reported(self):
        desired = [{"Source Key": "INVOICE:2026-10", "Invoice Count": 4},
                   {"Source Key": "INVOICE:2026-11", "Invoice Count": 5}]
        existing = [{"record_id": "oct", "fields": {
            "Source Key": "INVOICE:2026-10", "Invoice Count": 9}}]
        stats = parity.month_counts(desired, existing)
        self.assertEqual(stats["MISSING_CANONICAL_MONTHS"], 1)
        self.assertEqual(stats["DIFFERING_CANONICAL_MONTHS"], 1)

    def test_erp_forecast_target_fails_closed(self):
        with self.assertRaisesRegex(SafeError, "NON_MAIL_SOURCE"):
            parity.month_counts([], [{"record_id": "bad", "fields": {
                "Source Key": "FORECAST:2026-11"}}])

    def test_no_revenue_write_when_source_refuses(self):
        with mock.patch.dict("os.environ", {"FEISHU_BASE_APP_TOKEN": "UNRELATED"}), \
             mock.patch.object(parity, "auth") as auth, \
             mock.patch.object(parity, "read_canonical_sources") as source:
            with self.assertRaisesRegex(SafeError, "WRONG_FEISHU_BASE"):
                parity.revenue_audit()
            auth.assert_not_called()
            source.assert_not_called()

    def test_no_domain_blocks(self):
        with mock.patch.dict("os.environ", {"PARITY_DOMAIN": "invalid"}):
            with self.assertRaisesRegex(SafeError, "PARITY_DOMAIN_INVALID"):
                parity.main()


if __name__ == "__main__":
    unittest.main()
