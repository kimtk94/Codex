#!/usr/bin/env python3
"""Synthetic-only Feishu project view diagnostics and safety tests."""
import io
import json
import os
import sys
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_view_coverage_readonly as audit


def rec(i, payment="", stage="", progress="", invoice="", outstanding="", quote=""):
    return {"record_id": "rec" + str(i), "fields": {
        "Source Key": "KEY" + str(i), "Quote Full Name": "Quote " + str(i),
        "Payment State": payment, "Current Stage": stage, "Progress %": progress,
        "Invoice Gross M KRW": invoice, "Outstanding Balance M KRW": outstanding,
        "Quote Match State": quote}}


class ProjectViewCoverageTests(unittest.TestCase):
    def test_405_source_records_and_227_outside(self):
        source = [rec(i) for i in range(405)]
        allrecords, cohorts, outside = audit.membership(source, {
            "ACTIVE": source[:66], "BILLING": source[66:178], "ARCHIVED": []})
        self.assertEqual(len(allrecords), 405)
        self.assertEqual(len(cohorts["ACTIVE"]), 66)
        self.assertEqual(len(cohorts["BILLING"]), 112)
        self.assertEqual(len(outside), 227)

    def test_disjoint_and_all_source_keys_enforced(self):
        source = [rec(i) for i in range(200)]
        with self.assertRaisesRegex(RuntimeError, "PROJECT_VIEW_OVERLAP"):
            audit.membership(source, {
                "ACTIVE": source[:20], "BILLING": source[10:30], "ARCHIVED": []})
        with self.assertRaisesRegex(RuntimeError, "VIEW_HAS_MISSING_SOURCE_KEYS"):
            audit.membership(source, {
                "ACTIVE": [rec(10000)], "BILLING": [], "ARCHIVED": []})
        with self.assertRaisesRegex(RuntimeError, "SOURCE_PROJECT_KEY_INTEGRITY"):
            audit.membership(source + [rec(3)], {
                "ACTIVE": [], "BILLING": [], "ARCHIVED": []})

    def test_privacy_safe_payment_does_not_infer_bank_receipt(self):
        self.assertEqual(audit.payment_bucket("Unpaid"), "UNPAID_LIKE_NOT_BANK_VERIFIED")
        self.assertEqual(audit.payment_bucket("Paid"), "PAID_LIKE_NOT_BANK_VERIFIED")
        self.assertEqual(audit.payment_bucket("Partially paid"), "PARTIAL_LIKE_NOT_BANK_VERIFIED")
        self.assertEqual(audit.payment_bucket(""), "MISSING")
        self.assertEqual(audit.payment_bucket("Project Foo LLC"), "OTHER_UNVERIFIED")

    def test_progress_and_money_missing_are_not_zero(self):
        self.assertEqual(audit.quantity_bucket(""), "MISSING")
        self.assertEqual(audit.quantity_bucket("0"), "ZERO")
        self.assertEqual(audit.quantity_bucket("1.3"), "POSITIVE_UNVERIFIED")
        self.assertEqual(audit.quantity_bucket("-1"), "INVALID")
        self.assertEqual(audit.progress_bucket(""), "MISSING")
        self.assertEqual(audit.progress_bucket("0"), "EXACT_0")
        self.assertEqual(audit.progress_bucket("100"), "EXACT_100")
        self.assertEqual(audit.progress_bucket("101"), "INVALID")

    def test_private_raw_status_and_invoice_amount_never_logged(self):
        source = [rec(i) for i in range(150)]
        source[130] = rec(130, "PRIVATE_CUSTOMER", "PRIVATE_STAGE", "52",
                          "1234.56", "77.89", "PRIVATE_QUOTE_STATUS")
        sample = audit.classify([source[130]])
        self.assertEqual(sample["PAYMENT"], {"OTHER_UNVERIFIED": 1})
        self.assertEqual(sample["STAGE"], {"OTHER_STAGE": 1})
        self.assertEqual(sample["INVOICE_GROSS"], {"POSITIVE_UNVERIFIED": 1})
        self.assertNotIn("PRIVATE_CUSTOMER", str(sample))
        self.assertNotIn("1234.56", str(sample))
        self.assertNotIn("77.89", str(sample))

    def test_view_filter_metadata_does_not_emit_filter_values(self):
        view = {"property": {"filter_info": {"conjunction": "and", "conditions": [
            {"field_id": "field-payment", "operator": "is", "value": '["CUSTOMER_SECRET"]'},
            {"field_id": "field-other", "operator": "contains", "value": '["PRIVATE"]'}]}}}
        result = audit.filter_metadata(view, {
            "field-payment": "Payment State", "field-other": "Customer"})
        self.assertEqual(result["FILTER_PAYMENT_STATE_is"], 1)
        self.assertEqual(result["FILTER_OTHER_FIELD_contains"], 1)
        self.assertEqual(result["FILTER_CONDITIONS"], 2)
        self.assertNotIn("CUSTOMER_SECRET", str(result))
        self.assertNotIn("PRIVATE", str(result))

    def test_provider_matching_view_filter_proves_outside_condition_failure(self):
        source = [rec(i) for i in range(150)]
        for i, record in enumerate(source):
            record["fields"]["Workflow Lane"] = "ACTIVE" if i < 40 else "COMPLETED"
        index = audit.key_index(source)
        actual = {"KEY" + str(i) for i in range(40)}
        outside = set(index) - actual
        view = {"property": {"filter_info": {"conjunction": "and", "conditions": [
            {"field_id": "field-lane", "operator": "is", "value": '["ACTIVE"]'}]}}}
        result = audit.safe_filter_comparison(
            view, {"field-lane": "Workflow Lane"}, index, actual, outside)
        self.assertEqual(result["SIMULATION"], "MATCHES_PROVIDER_VIEW")
        self.assertEqual(result["FILTER_1_WORKFLOW_LANE_OUTSIDE_MATCH"], 0)
        self.assertEqual(result["FILTER_1_WORKFLOW_LANE_OUTSIDE_FAIL"], 110)
        self.assertNotIn("COMPLETED", str(result))

    def test_view_filter_with_mismatch_must_not_claim_reason(self):
        source = [rec(i) for i in range(150)]
        for i, record in enumerate(source):
            record["fields"]["Workflow Lane"] = "ACTIVE" if i < 40 else "OTHER"
        index = audit.key_index(source)
        actual = {"KEY" + str(i) for i in range(30)}
        outside = set(index) - actual
        view = {"property": {"filter_info": {"conjunction": "and", "conditions": [
            {"field_id": "lane", "operator": "is", "value": '["ACTIVE"]'}]}}}
        result = audit.safe_filter_comparison(
            view, {"lane": "Workflow Lane"}, index, actual, outside)
        self.assertEqual(result["SIMULATION"], "UNVERIFIED_MISMATCH")
        self.assertEqual(result["PREDICTED_ONLY"], 10)
        self.assertNotIn("FILTER_1_WORKFLOW_LANE_OUTSIDE_FAIL", result)

    def test_unsupported_filter_value_fail_closed(self):
        source = [rec(i) for i in range(150)]
        index = audit.key_index(source)
        view = {"property": {"filter_info": {"conjunction": "and", "conditions": [
            {"field_id": "lane", "operator": "contains", "value": '["secret"]'}]}}}
        result = audit.safe_filter_comparison(
            view, {"lane": "Workflow Lane"}, index, set(), set(index))
        self.assertEqual(result, {"SIMULATION": "UNSUPPORTED_FIELD_OR_OPERATOR"})

    def test_receipt_and_lane_labels_never_confused_with_bank_verification(self):
        self.assertEqual(audit.receipt_bucket("VERIFIED"), "VERIFIED_LABEL_ONLY")
        self.assertEqual(audit.present_bucket(""), "MISSING")
        self.assertEqual(audit.workflow_bucket("COMPLETED"), "COMPLETED_LIKE")
        self.assertEqual(audit.workflow_bucket("PAID"), "ARCHIVED_OR_PAID_LIKE_UNVERIFIED")

    def test_get_only_retries_same_page_for_timeout(self):
        seen = []
        def get(method, path, token=None):
            self.assertEqual(method, "GET")
            seen.append(path)
            if len(seen) == 1:
                raise TimeoutError("no response")
            return {"code": 0, "data": {"items": [
                {"record_id": "rec-one"}], "has_more": False}}
        with mock.patch.object(audit, "request", side_effect=get), \
             mock.patch.object(audit.time, "sleep") as sleeper:
            got = audit.pages("/dummy", "synthetic")
        self.assertEqual(len(got), 1)
        self.assertEqual(seen, [seen[0], seen[0]])
        sleeper.assert_called_once()

    def test_http_400_does_not_retry(self):
        with mock.patch.object(audit, "request",
                               side_effect=RuntimeError("HTTP 400 from /dummy")) as req, \
             mock.patch.object(audit.time, "sleep") as sleeper:
            with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                audit.pages("/dummy", "token")
        req.assert_called_once()
        sleeper.assert_not_called()

    def test_http_503_retries_and_exhausts_safely(self):
        with mock.patch.object(audit, "request",
                               side_effect=RuntimeError("HTTP 503 from /private")) as req, \
             mock.patch.object(audit.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "READ_ONLY_TRANSIENT_RETRY_EXHAUSTED") as ctx:
                audit.get_json("/private", "token")
        self.assertNotIn("/private", str(ctx.exception))
        self.assertEqual(req.call_count, audit.READ_MAX_RETRIES + 1)

    def test_no_view_data_writes_by_audit(self):
        source = [rec(i) for i in range(150)]
        def fake_get(path, token):
            if path.endswith("/views/" + audit.VIEW_IDS["ACTIVE"]):
                return {"view": {"view_id": audit.VIEW_IDS["ACTIVE"], "property": {
                    "filter_info": {"conditions": []}}}}
            if path.endswith("/views/" + audit.VIEW_IDS["BILLING"]):
                return {"view": {"view_id": audit.VIEW_IDS["BILLING"], "property": {
                    "filter_info": {"conditions": []}}}}
            if path.endswith("/views/" + audit.VIEW_IDS["ARCHIVED"]):
                return {"view": {"view_id": audit.VIEW_IDS["ARCHIVED"], "property": {
                    "filter_info": {"conditions": []}}}}
            self.fail("unexpected metadata path")
        def fake_pages(path, token, extra=None):
            if path.endswith("/fields"):
                return [{"field_id": "field1", "field_name": "Payment State"}]
            view = (extra or {}).get("view_id")
            if view == audit.VIEW_IDS["ACTIVE"]:
                return source[:30]
            if view == audit.VIEW_IDS["BILLING"]:
                return source[30:55]
            if view == audit.VIEW_IDS["ARCHIVED"]:
                return []
            if path.endswith("/records"):
                return source
            self.fail("unexpected record path")
        buf = io.StringIO()
        with mock.patch.object(audit, "pages", side_effect=fake_pages), \
             mock.patch.object(audit, "get_json", side_effect=fake_get), \
             redirect_stdout(buf):
            audit.audit("synthetic-token", audit.API)
        log = buf.getvalue()
        self.assertIn("PROJECT_COVERAGE_OUTSIDE_ALL_VIEWS=95", log)
        self.assertIn("PROJECT_VIEW_COVERAGE_AUDIT_PASS read_only=1 record_writes=0", log)
        self.assertNotIn("KEY149", log)

    def test_non_plan_mode_rejected_before_auth(self):
        with mock.patch.dict(os.environ, {"FEISHU_PROJECT_VIEW_AUDIT_MODE": "apply"}), \
             mock.patch.object(audit, "request") as request:
            with self.assertRaisesRegex(RuntimeError, "READ_ONLY_MODE_REQUIRED"):
                audit.main()
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
