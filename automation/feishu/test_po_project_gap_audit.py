#!/usr/bin/env python3
"""Contract-first project counting: no mention-only mail clears PO due."""
import json
import unittest
from unittest import mock
import po_project_gap_audit as g
import contract_po_tracker as po


C = "2026-11-04T10:00:00+09:00"
T = "2026-11-05T10:00:00+09:00"
L = "2026-11-06T10:00:00+09:00"
P = "AMEA2026042239"
Q = "AMEA2026042240"


def contract(project=P, when=C, **extra):
    return {"fields": {"Project ID": project, "Contract Notice UTC": when,
                        "Contract Mail Key": "contract-"+project,
                        "Contract Source": "CSS",
                        "PO Status": "PO_REQUIRED", **extra}}


def mail(project=P, body="Please submit the PO.", when=T, key="a", title="Project update",
         sender=po.CSS, **extra):
    fields = {"Mail Key": key, "Subject": title+" "+project if project else title,
              "Body Excerpt": body, "Direction": "INBOUND",
              "Received At": when, "In Reply To": "", "From": sender, **extra}
    if sender == po.CRM_SENDER:
        fields.update({"Source Account": po.CRM_ACCOUNT, "Source Filter": "EXACT_FROM_CRM"})
    return {"fields": fields}


def sources(css=None, crm=None):
    return {"QQ Mail Intake": css or [], "CRM Filtered Mail Intake": crm or []}


class ProjectGapTests(unittest.TestCase):
    def test_no_postcontract_mail_no_reduction(self):
        d = g.project_rows(sources(), [contract()])
        c = d["project_cohorts"]
        self.assertEqual(c["all_contract_projects"], 1)
        self.assertEqual(c["no_post_contract_po_mail"], 1)
        self.assertEqual(d["review_candidate_reduction"], 0)
        self.assertEqual(d["verified_receipt_reduction"], 0)

    def test_first_request_then_delivery_candidate_is_one_project(self):
        d = g.project_rows(sources(css=[
            mail(body="Please submit PO", when=T, key="r"),
            mail(body="We received PO", when=L, key="d"),
        ]), [contract()])
        c = d["project_cohorts"]
        self.assertEqual(c["post_contract_po_mail_total"], 2)
        self.assertEqual(c["projects_post_contract_repeated_po_mail"], 1)
        self.assertEqual(c["latest_POSITIVE_CANDIDATE"], 1)
        self.assertEqual(d["review_candidate_reduction"], 1)
        self.assertEqual(d["verified_receipt_reduction"], 0)

    def test_later_missing_overrides_earlier_delivery(self):
        d = g.project_rows(sources(css=[
            mail(body="PO was received", when=T, key="first"),
            mail(body="PO not received yet", when=L, key="latest"),
        ]), [contract()])
        self.assertEqual(d["project_cohorts"]["latest_MISSING_OR_NOT_RECEIVED"], 1)
        self.assertEqual(d["project_cohorts"]["projects_positive_ever_after_contract"], 1)
        self.assertEqual(d["review_candidate_reduction"], 0)

    def test_precontract_delivery_does_not_reduce_queue(self):
        d = g.project_rows(sources(css=[
            mail(body="We have received PO", when="2026-11-03T12:00:00+09:00"),
        ]), [contract()])
        self.assertEqual(d["project_cohorts"]["no_post_contract_po_mail"], 1)
        self.assertEqual(d["mail_matching"]["before_contract_or_contract_notice"], 1)

    def test_contract_mail_body_po_does_not_count_as_receipt(self):
        d = g.project_rows(sources(css=[
            mail(body="PO has been received", key="contract-"+P, when=C),
        ]), [contract()])
        self.assertEqual(d["review_candidate_reduction"], 0)
        self.assertEqual(d["mail_matching"]["before_contract_or_contract_notice"], 1)

    def test_same_time_separate_mail_not_proven_after_contract(self):
        d = g.project_rows(sources(css=[
            mail(body="We received the PO", when=C, key="different"),
        ]), [contract()])
        self.assertEqual(d["project_cohorts"]["no_post_contract_po_mail"], 1)
        self.assertEqual(d["mail_matching"]["same_timestamp_as_contract_different_mail"], 1)

    def test_body_only_id_never_auto_links(self):
        d = g.project_rows(sources(css=[
            mail(project=None, title="Weekly update",
                 body="We received the PO AMEA2026042239"),
        ]), [contract()])
        self.assertEqual(d["project_cohorts"]["no_post_contract_po_mail"], 1)
        self.assertEqual(d["mail_matching"]["po_mail_without_subject_project"], 1)
        self.assertEqual(d["writes"], 0)

    def test_latest_conflicting_notice_is_not_positive(self):
        d = g.project_rows(sources(css=[
            mail(body="We received PO", when=T, key="received"),
            mail(body="PO not received", when=T, key="missing"),
        ]), [contract()])
        self.assertEqual(d["project_cohorts"]["latest_conflicting_notice"], 1)
        self.assertEqual(d["review_candidate_reduction"], 0)

    def test_request_only_does_not_count_received(self):
        d = g.project_rows(sources(css=[
            mail(body="Please submit PO", when=T, key="a"),
            mail(body="PO pending", when=L, key="b"),
        ]), [contract()])
        self.assertEqual(d["project_cohorts"]["latest_REQUEST_OR_REMINDER"] +
                         d["project_cohorts"].get("latest_MENTION_ONLY", 0), 1)
        self.assertEqual(d["review_candidate_reduction"], 0)

    def test_body_only_po_with_subject_id_is_allowed_candidate_not_file(self):
        d = g.project_rows(sources(css=[
            mail(body="PO has been received", when=T, title="Progress"),
        ]), [contract()])
        self.assertEqual(d["project_cohorts"]["projects_body_only_po_after_contract"], 1)
        self.assertEqual(d["review_candidate_reduction"], 1)
        self.assertEqual(d["verified_receipt_reduction"], 0)

    def test_multiple_contracts_partition_and_no_customer_data_leaks(self):
        d = g.project_rows(sources(css=[
            mail(project=P, body="PO has been received", key="m1"),
            mail(project=Q, body="Please send the PO", key="m2"),
        ]), [contract(P), contract(Q), contract("AMEA2026042242")])
        c=d["project_cohorts"]
        self.assertEqual(c["all_contract_projects"], 3)
        self.assertEqual(c["no_post_contract_po_mail"], 1)
        self.assertEqual(c["latest_REQUEST_OR_REMINDER"], 1)
        self.assertEqual(c["latest_POSITIVE_CANDIDATE"], 1)
        serial=json.dumps(d)
        self.assertNotIn(P,serial)
        self.assertNotIn(Q,serial)
        self.assertNotIn("m1",serial)
        self.assertEqual(d["action"],"READ_ONLY_NO_STATUS_CHANGES_NO_MANUAL_LINKS")

    def test_manual_document_attestation_does_not_come_from_body(self):
        d=g.project_rows(sources(css=[
            mail(body="PO mentioned",key="x"),
        ]), [contract(**{
            "PO Document Verification":"FILE_VERIFIED",
            "PO Document Reference":"internal:po-1",
            "PO Verified By":"reviewer",
            "PO Verified At":"2026-11-06T10:00:00+09:00"})])
        self.assertEqual(d["verified_receipt_reduction"],1)
        self.assertEqual(d["review_candidate_reduction"],0)

    def test_inferred_submitted_counter_separate_from_verified_receipt(self):
        tracker=contract(**{
            "PO Followup Queue": "PO_SUBMITTED_INFERRED",
            "Submission Inference": "ASSUMED_BY_DOWNSTREAM_NOTICE",
            "Downstream Evidence Type": "FINAL_REPORT",
            "Downstream Evidence UTC": "2026-11-05T10:00:00+09:00",
            "Downstream Mail Key": "downstream-evidence",
        })
        result=g.project_rows(sources(),[tracker])
        self.assertEqual(result["inferred_po_submitted_projects"], 1)
        self.assertEqual(result["operational_po_missing_projects"], 0)
        self.assertEqual(result["verified_receipt_reduction"], 0)

    def test_inferred_status_without_evidence_fails_closed(self):
        tracker=contract(**{"PO Followup Queue": "PO_SUBMITTED_INFERRED",
                            "Submission Inference": "ASSUMED_BY_DOWNSTREAM_NOTICE"})
        with self.assertRaisesRegex(g.SafeError,"INFERRED_SUBMISSION_PROOF_INVALID"):
            g.project_rows(sources(),[tracker])

    def test_precontract_downstream_evidence_cannot_close_queue(self):
        tracker=contract(**{
            "PO Followup Queue": "PO_SUBMITTED_INFERRED",
            "Submission Inference": "ASSUMED_BY_DOWNSTREAM_NOTICE",
            "Downstream Evidence Type": "STATEMENT",
            "Downstream Evidence UTC": "2026-11-03T10:00:00+09:00",
            "Downstream Mail Key": "a",
        })
        with self.assertRaisesRegex(g.SafeError,"INFERRED_SUBMISSION_PROOF_INVALID"):
            g.project_rows(sources(),[tracker])

    def test_distinct_contract_projects_count_inferred_and_due(self):
        tracker1=contract(P, **{
            "PO Followup Queue": "PO_SUBMITTED_INFERRED",
            "Submission Inference": "ASSUMED_BY_DOWNSTREAM_NOTICE",
            "Downstream Evidence Type": "FINAL_REPORT_AND_STATEMENT",
            "Downstream Evidence UTC": "2026-11-05T10:00:00+09:00",
            "Downstream Mail Key": "one",
        })
        tracker2=contract(Q, **{"PO Followup Queue": "PO_REQUIRED"})
        result=g.project_rows(sources(),[tracker1,tracker2])
        self.assertEqual(result["project_cohorts"]["all_contract_projects"],2)
        self.assertEqual(result["inferred_po_submitted_projects"],1)
        self.assertEqual(result["operational_po_missing_projects"],1)

    def test_crm_contract_legacy_record_excluded_not_counted(self):
        prior=contract("AMEA2026042244", **{
            "Contract Source": "CRM",
            "PO Followup Queue": "EXCLUDED_NO_OWNER_CONTRACT",
        })
        report=g.project_rows(sources(),[contract(),prior])
        self.assertEqual(report["project_cohorts"]["all_contract_projects"],1)
        self.assertEqual(report["excluded_other_sales_or_unconfirmed_contract_projects"],1)

    def test_crm_contract_in_po_required_queue_fails_closed(self):
        prior=contract("AMEA2026042244",**{
            "Contract Source": "CRM",
            "PO Followup Queue": "PO_REQUIRED",
        })
        with self.assertRaisesRegex(g.SafeError,"NON_OWNER_CONTRACT_IN_DUE_QUEUE"):
            g.project_rows(sources(),[prior])

    def test_duplicate_source_mail_fails_closed(self):
        with self.assertRaisesRegex(g.SafeError,"SOURCE_MAIL_DUPLICATE"):
            g.project_rows(sources(css=[mail(key="dup"),mail(key="dup")]),[contract()])

    def test_contract_missing_timestamp_fails(self):
        with self.assertRaisesRegex(g.SafeError,"CONTRACT_TRACKER_INVALID"):
            g.project_rows(sources(),[contract(when="")])

    def test_invalid_source_sender_not_counted(self):
        d=g.project_rows(sources(css=[mail(sender="other@example.net")]),[contract()])
        self.assertEqual(d["project_cohorts"]["no_post_contract_po_mail"],1)

    def test_wrong_base_fails_before_auth(self):
        with mock.patch.dict(g.os.environ,{"FEISHU_BASE_APP_TOKEN":"wrong"}),mock.patch.object(g,"auth") as a:
            with self.assertRaisesRegex(g.SafeError,"WRONG_FEISHU_BASE"):
                g.main()
            a.assert_not_called()


if __name__ == "__main__":
    unittest.main()
