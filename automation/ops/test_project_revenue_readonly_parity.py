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
