#!/usr/bin/env python3
"""Original PO mail subject+body excerpt regression, no document proof guesses."""
import unittest
from unittest import mock
import po_body_multiplicity_audit as a
import contract_po_tracker as po

def row(subject, body="", source=po.CSS, uid="1", **extra):
    f = {"Mail Key": uid, "From": source, "Direction": "INBOUND",
         "Received At": "2026-11-06T10:00:00+09:00", "Subject": subject,
         "Body Excerpt": body, "In Reply To": ""}
    f.update(extra)
    return {"fields": f}

class PoBodyAnalysisTests(unittest.TestCase):
    def test_body_only_po_detected_but_not_used_as_project_identity(self):
        r=a.classify(row("Weekly notice", "Please send PO AMEA2026042239")["fields"],po.CSS,"QQ Mail Intake")
        self.assertEqual(r["body_signal"],"BODY_REQUEST_REMINDER_CANDIDATE")
        self.assertTrue(r["body_only"])
        self.assertTrue(r["body_project_candidate_untrusted"])
        self.assertIsNone(r["project"])

    def test_received_claim_is_review_only(self):
        r=a.classify(row("Project AMEA2026042239","PO has been received")["fields"],po.CSS,"QQ Mail Intake")
        self.assertEqual(r["body_signal"],"BODY_DELIVERY_CLAIM_REVIEW")
        self.assertFalse(r["body_file_word_only"])

    def test_negative_po_not_received_outweighs_received(self):
        self.assertEqual(a.body_signal("Our PO has not been received yet"),
                         "BODY_MISSING_OR_NOT_RECEIVED_CANDIDATE")

    def test_approved_is_not_verified_file(self):
        r=a.classify(row("Project AMEA2026042239","PO approved and attached")["fields"],po.CSS,"QQ Mail Intake")
        self.assertEqual(r["body_signal"],"BODY_APPROVAL_CLAIM_REVIEW")
        self.assertTrue(r["body_file_word_only"])

    def test_context_words_far_away_not_assigned_to_po(self):
        body="We received the sequencing report. "+"x"*350+" PO number: 12345"
        self.assertEqual(a.body_signal(body),"BODY_PO_NUMBER_ONLY")

    def test_no_po_in_title_or_body_is_ignored(self):
        self.assertIsNone(a.classify(row("Invoice AMEA2026042239","The report is ready")["fields"],po.CSS,"QQ Mail Intake"))

    def test_truncated_body_is_flagged(self):
        r=a.classify(row("PO AMEA2026042239","x"*1800)["fields"],po.CSS,"QQ Mail Intake")
        self.assertTrue(r["body_near_excerpt_limit"])

    def test_source_provenance_rules(self):
        invalid = row("PO Received AMEA2026042239",source="crm@novogene.com.fake")
        self.assertIsNone(a.classify(invalid["fields"],po.CRM_SENDER,"CRM Filtered Mail Intake"))
        invalid2=row("PO Received AMEA2026042239",source=po.CRM_SENDER,
                     **{"Source Account":"wrong","Source Filter":"EXACT_FROM_CRM"})
        self.assertIsNone(a.classify(invalid2["fields"],po.CRM_SENDER,"CRM Filtered Mail Intake"))
        valid=row("PO Received AMEA2026042239",source=po.CRM_SENDER,
                     **{"Source Account":po.CRM_ACCOUNT,"Source Filter":"EXACT_FROM_CRM"})
        self.assertIsNotNone(a.classify(valid["fields"],po.CRM_SENDER,"CRM Filtered Mail Intake"))

    def test_reply_and_non_inbound_rejected(self):
        self.assertIsNone(a.classify(row("Re: PO Received AMEA2026042239")["fields"],po.CSS,"QQ Mail Intake"))
        self.assertIsNone(a.classify(row("PO Received AMEA2026042239",Direction="OUTBOUND")["fields"],po.CSS,"QQ Mail Intake"))

    def test_project_multiplicity_and_unique_contract_intersection(self):
        source={"QQ Mail Intake":[
            row("PO request AMEA2026042239","Please send PO",uid="q1"),
            row("PO reminder AMEA2026042239","PO not received yet",uid="q2"),
            row("PO received AMEA2026042240","We received PO",uid="q3"),
            row("Weekly update","Attached PO AMEA2026042239",uid="q4"),
        ],"CRM Filtered Mail Intake":[]}
        report=a.summarize(source,["AMEA2026042239"])
        self.assertEqual(report["po_mail_categories"]["po_relevant_mail"],4)
        self.assertEqual(report["repeat_project_counts"]["projects_with_po_mail"],2)
        self.assertEqual(report["repeat_project_counts"]["projects_with_multiple_po_mails"],1)
        self.assertEqual(report["repeat_project_counts"]["max_mails_per_project"],2)
        self.assertEqual(report["contract_context"]["po_mails_for_existing_contracts"],2)
        self.assertEqual(report["po_mail_categories"]["unlinked_no_subject_project"],1)
        self.assertEqual(report["manual_links"],0)
        self.assertNotIn("AMEA2026042239",str(report))

    def test_duplicate_mail_key_fails_closed(self):
        source={"QQ Mail Intake":[
            row("PO AMEA2026042239",uid="dup"),
            row("PO AMEA2026042240",uid="dup"),
        ],"CRM Filtered Mail Intake":[]}
        with self.assertRaisesRegex(a.SafeError,"DUPLICATE_MAIL_KEY"):
            a.summarize(source)

    def test_wrong_base_no_auth(self):
        with mock.patch.dict(a.os.environ,{"FEISHU_BASE_APP_TOKEN":"bad"}),mock.patch.object(a,"auth") as auth:
            with self.assertRaisesRegex(a.SafeError,"WRONG_BASE"):
                a.main()
            auth.assert_not_called()

if __name__=="__main__":
    unittest.main()
