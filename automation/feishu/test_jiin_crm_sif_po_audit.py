#!/usr/bin/env python3
"""Offline regression for CRM SIF/PO status distinctions and guardrails."""
import unittest

import jiin_crm_sif_po_audit as a
from jiin_crm_filtered_ingest import mail_key


def record(subject, uid="1", received="2026-11-06T09:00:00+09:00", body="", **overrides):
    fields = {
        "Mail Key": mail_key("99", uid),
        "From": "crm@novogene.com",
        "Source Account": "jiin.yoo@novogene.com",
        "Source Filter": "EXACT_FROM_CRM",
        "Received At": received,
        "Direction": "INBOUND",
        "Subject": subject,
        "Body Excerpt": body,
        "AMEA": "",
        "H Project": "",
        "In Reply To": "",
    }
    fields.update(overrides)
    return {"record_id": "rec" + uid, "fields": fields}


class SifPoAuditTests(unittest.TestCase):
    def test_sif_request_submission_receipt_and_approval(self):
        self.assertEqual(a.evidence("Please Submit SIF", "", "SIF"), "ACTION_REQUESTED")
        self.assertEqual(a.evidence("SIF submitted", "", "SIF"), "SUBMITTED_NOTICE")
        self.assertEqual(a.evidence("SIF Received", "", "SIF"), "RECEIVED_NOTICE")
        self.assertEqual(a.evidence("SIF Approved", "", "SIF"), "APPROVED_NOTICE")
        self.assertEqual(a.evidence("SIF rejected", "", "SIF"), "REJECTED_NOTICE")
        self.assertEqual(a.evidence("SIF not approved", "", "SIF"), "REJECTED_NOTICE")

    def test_po_request_pending_received_and_confirmed(self):
        self.assertEqual(a.evidence("Please Submit PO", "", "PO"), "ACTION_REQUESTED")
        self.assertEqual(a.evidence("PO not received", "", "PO"), "NOT_RECEIVED_NOTICE")
        self.assertEqual(a.evidence("No PO received", "", "PO"), "NOT_RECEIVED_NOTICE")
        self.assertEqual(a.evidence("PO has not been received", "", "PO"), "NOT_RECEIVED_NOTICE")
        self.assertEqual(a.evidence("Purchase Order Received", "", "PO"), "RECEIVED_NOTICE")
        self.assertEqual(a.evidence("PO Approved", "", "PO"), "CONFIRMED_NOTICE")
        self.assertEqual(a.evidence("PO Number: 1234", "", "PO"), "MENTION_ONLY")

    def test_reply_and_body_quote_never_confirm_receipt(self):
        self.assertEqual(a.evidence("Monthly status", "PO Approved", "PO"), "MENTION_ONLY")
        self.assertEqual(a.evidence("Re: SIF Approved", "", "SIF"), "MENTION_ONLY")
        self.assertEqual(a.evidence("PO Received", "", "PO", True), "MENTION_ONLY")

    def test_other_words_not_purchase_order(self):
        self.assertEqual(a.evidence("Status report", "position posted", "PO"), "NOT_OBSERVED")
        self.assertEqual(a.evidence("SIF", "", "PO"), "NOT_OBSERVED")

    def test_identifiers_dont_merge_unverified_projects(self):
        self.assertEqual(a.project_identifier(record("SIF Approved AMEA2026042239")["fields"]),
                         ("AMEA2026042239", False))
        self.assertEqual(a.project_identifier(record("PO Received AMEA2026042239 AMEA2026042240")["fields"]),
                         (None, True))

    def test_latest_notice_wins(self):
        rows = [
            record("SIF Approved AMEA2026042239", uid="1",
                   received="2026-11-05T10:00:00+09:00"),
            record("Please Submit SIF AMEA2026042239", uid="2",
                   received="2026-11-06T10:00:00+09:00"),
            record("PO Received AMEA2026042239", uid="3",
                   received="2026-11-06T11:00:00+09:00"),
        ]
        result = a.audit_rows(rows)
        self.assertEqual(result["source_rows"], 3)
        self.assertEqual(result["projects_with_sif_po_evidence"], 1)
        self.assertEqual(result["projects_requiring_review"], 1)
        self.assertEqual(result["sif_messages"]["ACTION_REQUESTED"], 1)
        self.assertEqual(result["po_messages"]["RECEIVED_NOTICE"], 1)

    def test_same_timestamp_conflict_needs_review(self):
        rows = [
            record("PO Received AMEA2026042239", uid="1"),
            record("PO not received AMEA2026042239", uid="2"),
        ]
        self.assertEqual(a.audit_rows(rows)["projects_requiring_review"], 1)

    def test_without_identifier_not_auto_associated(self):
        result = a.audit_rows([record("Please Submit PO")])
        self.assertEqual(result["projects_with_sif_po_evidence"], 0)
        self.assertEqual(result["unlinked_actionable_messages"], 1)

    def test_source_sender_guard_precedes_classification(self):
        from qq_mail_ingest import SafeError
        with self.assertRaisesRegex(SafeError, "WRONG_SENDER"):
            a.audit_rows([record("PO Received AMEA2026042239", From="crm@novogene.com.fake")])


if __name__ == "__main__":
    unittest.main()
