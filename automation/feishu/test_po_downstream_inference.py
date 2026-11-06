#!/usr/bin/env python3
"""Post-Contract downstream milestone makes PO submission assumed, not file-proven."""
import unittest
from unittest import mock
import contract_po_tracker as p


def mail(subject, uid="one", at="2026-11-06T10:00:00+09:00", sender=p.CSS, **overrides):
    row = {
        "Mail Key": "key-" + uid, "Subject": subject, "From": sender,
        "Direction": "INBOUND", "In Reply To": "", "Received At": at,
    }
    row.update(overrides)
    return row


def ev(subject, **params):
    row = mail(subject, **params)
    return p.event(row, row["From"])


def item(*events):
    return p.build_tracker(events, "testtime")[0]


class FinalReportStatementPOTests(unittest.TestCase):
    def test_final_report_ready_marks_po_submitted_assumed(self):
        c = ev("Contract Ready AMEA2026042239", uid="c")
        f = ev("Final Report Ready AMEA2026042239", uid="report",
               at="2026-11-06T11:00:00+09:00")
        self.assertEqual(f["downstream"], {"FINAL_REPORT"})
        result = item(c, f)
        p.apply_followup([result], {})
        self.assertEqual(result["PO Status"], "PO_REQUIRED")  # Mail-only state preserved.
        self.assertEqual(result["PO Followup Queue"], "PO_SUBMITTED_INFERRED")
        self.assertEqual(result["Submission Inference"], "ASSUMED_BY_DOWNSTREAM_NOTICE")
        self.assertEqual(result["Downstream Evidence Type"], "FINAL_REPORT")
        self.assertEqual(result["Downstream Mail Key"], "key-report")
        self.assertEqual(result["Next Action"], "NO_PO_REQUEST_FINAL_REPORT_OR_STATEMENT")
        self.assertNotIn("PO Document Verification", result)

    def test_statement_ready_issued_and_confirmed_each_clears_followup(self):
        for status in ("Ready", "Issued", "Confirmed"):
            with self.subTest(status=status):
                c = ev("Contract Created AMEA2026042239", uid="c")
                s = ev("Statement " + status + " AMEA2026042239", uid="statement",
                       at="2026-11-06T11:00:00+09:00", sender=p.CRM_SENDER)
                result = item(c, s)
                p.apply_followup([result], {})
                self.assertEqual(result["PO Followup Queue"], "PO_SUBMITTED_INFERRED")
                self.assertEqual(result["Downstream Source"], "CRM")

    def test_combined_final_report_statement_notice_is_one_project(self):
        c = ev("Contract Ready AMEA2026042239", uid="c")
        report = ev("Final Report & Statement Ready AMEA2026042239", uid="both",
                    at="2026-11-06T11:00:00+09:00")
        result = item(c, report)
        p.apply_followup([result], {})
        self.assertEqual(result["Downstream Evidence Type"], "FINAL_REPORT_AND_STATEMENT")
        self.assertEqual(result["PO Followup Queue"], "PO_SUBMITTED_INFERRED")

    def test_two_milestones_still_one_project(self):
        c = ev("Contract Ready AMEA2026042239", uid="c")
        report = ev("Final Report Released AMEA2026042239", uid="r",
                    at="2026-11-06T11:00:00+09:00")
        stmt = ev("Statement Issued AMEA2026042239", uid="s",
                  at="2026-11-06T12:00:00+09:00")
        results = p.build_tracker([c, report, stmt], "now")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["Downstream Evidence Type"], "FINAL_REPORT_AND_STATEMENT")
        self.assertEqual(results[0]["Downstream Mail Key"], "key-s")

    def test_downstream_before_contract_is_not_submission(self):
        f = ev("Final Report Ready AMEA2026042239", uid="r",
               at="2026-11-06T09:00:00+09:00")
        c = ev("Contract Ready AMEA2026042239", uid="c",
               at="2026-11-06T10:00:00+09:00")
        result = item(f, c)
        p.apply_followup([result], {})
        self.assertEqual(result["PO Followup Queue"], "PO_REQUIRED")
        self.assertEqual(result["Submission Inference"], "NOT_OBSERVED")

    def test_downstream_same_timestamp_as_contract_is_not_submission(self):
        f = ev("Statement Ready AMEA2026042239", uid="r")
        c = ev("Contract Ready AMEA2026042239", uid="c")
        result = item(c, f)
        p.apply_followup([result], {})
        self.assertEqual(result["PO Followup Queue"], "PO_REQUIRED")

    def test_downstream_without_verified_contract_does_not_create_project(self):
        f = ev("Final Report & Statement Ready AMEA2026042239")
        self.assertEqual(p.build_tracker([f], "now"), [])

    def test_negative_and_draft_milestones_not_promoted(self):
        for title in (
            "Final Report Not Ready AMEA2026042239",
            "Statement pending AMEA2026042239",
            "Draft Statement AMEA2026042239",
            "Statement Requested AMEA2026042239",
            "Final Report ready but Statement cancelled AMEA2026042239",
            "Statement of Work Ready AMEA2026042239",
            "Final Report failed AMEA2026042239",
        ):
            with self.subTest(title=title):
                self.assertIsNone(ev(title))

    def test_report_without_positive_ready_signal_is_not_enough(self):
        self.assertIsNone(ev("Final Report status update AMEA2026042239"))
        self.assertIsNone(ev("Statement question AMEA2026042239"))

    def test_untrusted_sender_and_unidentified_subject_cannot_infer(self):
        self.assertIsNone(p.event(mail("Final Report Ready AMEA2026042239",
                                        sender="someone@example.com"), p.CSS))
        self.assertIsNone(ev("Final Report Ready"))
        self.assertIsNone(ev("Final Report Ready AMEA2026042239 AMEA2026042240"))
        self.assertIsNone(ev("Re: Final Report Ready AMEA2026042239"))
        self.assertIsNone(ev("Final Report Ready AMEA2026042239",
                             **{"In Reply To": "<quoted@x>"}))
        self.assertIsNone(ev("Final Report Ready AMEA2026042239",
                             at="2025-11-06T10:00:00+09:00"))
        self.assertIsNone(ev("Final Report Ready AMEA2026042239",
                             Direction="OUTBOUND"))

    def test_body_only_report_is_not_used_to_infer(self):
        self.assertIsNone(ev("Project update AMEA2026042239",
                             **{"Body Excerpt": "Final Report & Statement Ready"}))

    def test_later_po_missing_notice_moves_to_conflict_review(self):
        c = ev("Contract Ready AMEA2026042239", uid="c")
        f = ev("Final Report Ready AMEA2026042239", uid="report",
               at="2026-11-06T11:00:00+09:00")
        negative = ev("PO not received AMEA2026042239", uid="missing",
                      at="2026-11-06T12:00:00+09:00")
        result = item(c, f, negative)
        p.apply_followup([result], {})
        self.assertEqual(result["Submission Inference"], "CONFLICT_REVIEW")
        self.assertEqual(result["PO Followup Queue"], "PO_EVIDENCE_CONFLICT_REVIEW")

    def test_earlier_po_request_does_not_override_report(self):
        c = ev("Contract Ready AMEA2026042239", uid="c")
        req = ev("Please Submit PO AMEA2026042239", uid="request",
                 at="2026-11-06T10:30:00+09:00")
        f = ev("Final Report Ready AMEA2026042239", uid="report",
               at="2026-11-06T11:00:00+09:00")
        result = item(c, req, f)
        p.apply_followup([result], {})
        self.assertEqual(result["PO Followup Queue"], "PO_SUBMITTED_INFERRED")

    def test_file_attestation_precedence_is_preserved(self):
        c = ev("Contract Ready AMEA2026042239", uid="c")
        f = ev("Statement Confirmed AMEA2026042239", uid="s",
               at="2026-11-06T11:00:00+09:00")
        result = item(c, f)
        previous = {
            "PO Document Verification": "FILE_VERIFIED",
            "PO Document Reference": "internal:document-reference",
            "PO Verified By": "Reviewer",
            "PO Verified At": "2026-11-06T12:00:00+09:00",
        }
        p.apply_followup([result], {"AMEA2026042239": {"fields": previous}})
        self.assertEqual(result["PO Followup Queue"], "FILE_VERIFIED_ATTESTED")
        self.assertEqual(result["Submission Inference"], "ASSUMED_BY_DOWNSTREAM_NOTICE")
        self.assertNotIn("PO Document Reference", result)

    def test_explicit_received_notice_keeps_file_review(self):
        c = ev("Contract Ready AMEA2026042239", uid="c")
        f = ev("Final Report Ready AMEA2026042239", uid="r",
               at="2026-11-06T11:00:00+09:00")
        received = ev("PO received AMEA2026042239", uid="po",
                      at="2026-11-06T12:00:00+09:00")
        result = item(c, f, received)
        p.apply_followup([result], {})
        self.assertEqual(result["PO Followup Queue"], "PO_FILE_REVIEW")
        self.assertEqual(result["PO Status"], "PO_RECEIVED_NOTICE")

    def test_schema_exposes_evidence_mail_and_provenance(self):
        for name in ("Downstream Evidence Type", "Downstream Evidence UTC",
                     "Downstream Source", "Downstream Mail Key",
                     "Submission Inference"):
            self.assertIn(name, p.FIELDS)


if __name__ == "__main__":
    unittest.main()
