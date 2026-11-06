#!/usr/bin/env python3
"""Aggregate-only SIF / PO issue audit: no project identity inference."""
import json
import unittest
from unittest import mock

import sif_po_issue_diagnostics as d
import contract_po_tracker as po
from jiin_crm_filtered_ingest import ACCOUNT


def rec(subject, sender=po.CSS, key="m1", body="", **extra):
    fields = {
        "Mail Key": key,
        "From": sender,
        "Direction": "INBOUND",
        "Received At": "2026-11-06T10:00:00+09:00",
        "In Reply To": "",
        "Subject": subject, "Body Excerpt": body,
    }
    fields.update(extra)
    return {"fields": fields, "record_id": key}


class IssueAuditTests(unittest.TestCase):
    def test_unlinked_causes_are_separate_and_no_auto_link(self):
        source = {"QQ Mail Intake": [
            rec("Please Submit SIF", body="AMEA2026042239", key="a"),
            rec("SIF Approved AMEA2026042239 AMEA2026042240", key="b"),
            rec("SIF Received X209SC26100001 H209SC26000002", key="c"),
            rec("Contract Ready AMEA2026042239", key="contract"),
            rec("SIF Approved AMEA2026042239", key="good"),
        ], "CRM Filtered Mail Intake": []}
        result = d.compute(source)
        self.assertEqual(result["sif_notices"]["subject_notice_unlinked"], 3)
        self.assertEqual(result["unlinked_reasons"]["NO_PROJECT_ID_IN_SUBJECT"], 1)
        self.assertEqual(result["unlinked_reasons"]["MULTIPLE_AMEA_IN_SUBJECT"], 1)
        self.assertEqual(result["unlinked_reasons"]["MULTIPLE_X_H_IN_SUBJECT"], 1)
        self.assertEqual(result["unlinked_reasons"]["UNLINKED_WITH_BODY_IDENTIFIER_CANDIDATE_NOT_USED"], 1)
        self.assertEqual(result["sif_approval_notice_projects"], 1)
        self.assertEqual(result["tracker_sync_consistency"]["po_source_projects"], 1)
        self.assertEqual(result["policy"], "NO_MANUAL_LINKING_NO_GUESSED_JOINS_READ_ONLY")
        # No customer name, subject, email body, or project identifier in report.
        serial = json.dumps(result)
        self.assertNotIn("AMEA2026042239", serial)
        self.assertNotIn("SIF Approved", serial)
        self.assertNotIn("m1", serial)

    def test_contract_missing_sif_and_po_no_receipt_notice(self):
        source = {"QQ Mail Intake": [rec("Contract Ready AMEA2026042239")],
                  "CRM Filtered Mail Intake": []}
        result = d.compute(source)
        self.assertEqual(result["sif_project_statuses"]["SIF_NOT_OBSERVED"], 1)
        self.assertEqual(result["sif_contract_projects_without_notice"], 1)
        self.assertEqual(result["po_source_statuses"]["PO_REQUIRED"], 1)

    def test_wrong_namespace_or_sender_not_trusted(self):
        source = {"QQ Mail Intake": [
            rec("SIF Approved AMEA2026042239", sender="fake@evil.com"),
        ], "CRM Filtered Mail Intake": [
            rec("SIF Approved AMEA2026042240", sender=po.CRM_SENDER,
                **{"Source Account": "wrong", "Source Filter": "EXACT_FROM_CRM"}),
            rec("SIF Approved AMEA2026042241", sender=po.CRM_SENDER,
                **{"Source Account": ACCOUNT, "Source Filter": "EXACT_FROM_CRM",
                   "Mail Key": "valid"}),
        ]}
        result = d.compute(source)
        self.assertEqual(result["sif_approval_notice_projects"], 1)
        self.assertEqual(result["mail_sources"]["original_CRM"], 1)

    def test_body_only_sif_not_promoted_to_approval(self):
        source = {"QQ Mail Intake": [
            rec("Status AMEA2026042239", body="SIF Approved"),
        ], "CRM Filtered Mail Intake": []}
        result = d.compute(source)
        self.assertEqual(result["unlinked_reasons"]["SIF_BODY_ONLY_MENTION_EXCLUDED"], 1)
        self.assertEqual(result["sif_approval_notice_projects"], 0)

    def test_file_attested_and_incomplete_attestation_not_merged(self):
        source = {"QQ Mail Intake": [rec("Contract Ready AMEA2026042239")],
                  "CRM Filtered Mail Intake": []}
        tracker = [{
            "fields": {"Project ID": "AMEA2026042239",
                "PO Document Verification": "FILE_VERIFIED",
                "PO Document Reference": "document-1",
                "PO Verified By": "reviewer",
                "PO Verified At": "2026-11-06T11:00:00+09:00"},
        }]
        res = d.compute(source, po_tracker_rows=tracker)
        self.assertEqual(res["po_file_verification"]["file_attested"], 1)
        tracker[0]["fields"]["PO Verified By"] = ""
        res = d.compute(source, po_tracker_rows=tracker)
        self.assertEqual(res["po_file_verification"]["partial_or_invalid_attestation"], 1)

    def test_tracker_mismatch_marked_not_silently_repaired(self):
        source = {"QQ Mail Intake": [rec("Contract Ready AMEA2026042239")],
                  "CRM Filtered Mail Intake": []}
        res = d.compute(source, [], [])
        self.assertEqual(res["tracker_sync_consistency"]["po_missing_from_tracker"], 1)
        self.assertTrue(res["tracker_sync_consistency"]["sif_tracker_count_mismatch"])
        self.assertEqual(res["writes"], 0)

    def test_duplicate_po_tracker_project_fails_closed(self):
        source = {"QQ Mail Intake": [], "CRM Filtered Mail Intake": []}
        tracker = [{"fields": {"Project ID": "AMEA2026042239"}}] * 2
        with self.assertRaisesRegex(d.SafeError, "DUPLICATE_OR_EMPTY_PO_PROJECT_ID"):
            d.compute(source, tracker)

    def test_reply_excluded_and_no_identifier_leak(self):
        source = {"QQ Mail Intake": [
            rec("Re: SIF Approved AMEA2026042239"),
            rec("SIF Approved AMEA2026042240", key="reply", **{"In Reply To": "<message>"}),
            rec("SIF Approved AMEA2026042241", key="outbound", Direction="OUTBOUND"),
        ], "CRM Filtered Mail Intake": []}
        res = d.compute(source)
        self.assertEqual(res["sif_notices"], {})
        self.assertEqual(res["mail_sources"], {})

    def test_wrong_base_fails_before_authentication(self):
        with mock.patch.dict(d.os.environ, {"FEISHU_BASE_APP_TOKEN": "wrong"}), \
             mock.patch.object(d, "auth") as auth:
            with self.assertRaisesRegex(d.SafeError, "WRONG_BASE"):
                d.main()
            auth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
