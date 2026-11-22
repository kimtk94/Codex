"""Synthetic owner-review cases: even completed requests cannot write."""
import json
import unittest
from datetime import datetime, timezone

from automation.css_mail.qq_replay_stage_request_readonly import (
    assess_requests, REQUEST_HEADER, CONFIRMATION, REQUEST_TAB,
)
from automation.css_mail.test_qq_replay_private_review_readonly import fixture
from automation.css_mail.test_qq_replay_plan_readonly import sample

NOW=datetime(2026,11,23,1,30,tzinfo=timezone.utc)

def data():
    plan,review,extract,stage,canonical=sample()
    rows=[]
    for i,p in enumerate(plan):
        r=review[i]
        rows.append({
            "No.":str(i+1),"Invoice Number":p["invoice_number"],
            "Amount KRW":p["amount_krw"],
            "IMAP UID":p["imap_uid"], "UIDVALIDITY":"201",
            "Original PDF Filename":p["filename"],
            "Scope":"QQ_STAGE_ONLY",
            "Review Status":r["Review Selection (NOT WRITE APPROVAL)"],
            "Execution Request":"NOT_REQUESTED",
            "Confirmation Phrase":"","Requested By":"",
            "Requested At UTC":"","Authorization Status":"NOT_AUTHORIZED",
            "Request Notes":"",
        })
    return rows,review,plan

class RequestTests(unittest.TestCase):
    def test_all_seven_absent_approval_and_no_stage_writes(self):
        result=assess_requests(*data(),NOW)
        self.assertEqual(result["request_not_requested_count"],7)
        self.assertEqual(result["request_status"],"HOLD")
        self.assertEqual(result["request_stage_writes"],0)
        self.assertEqual(result["request_authenticated_approvals"],0)
        self.assertNotIn("123456789",json.dumps(result))
    def test_seven_completed_request_rows_still_not_authority(self):
        rows,review,plan=data()
        for i in range(7):
            review[i]["Review Selection (NOT WRITE APPROVAL)"]="REVIEW_OK"
            rows[i].update({
                "Review Status":"REVIEW_OK",
                "Execution Request":"REQUEST_STAGE_ONLY",
                "Confirmation Phrase":CONFIRMATION,
                "Requested By":"synthetic_owner",
                "Requested At UTC":"2026-11-23T01:00:00Z",
            })
        result=assess_requests(rows,review,plan,NOW)
        self.assertEqual(result["request_ready_for_separate_review_count"],7)
        self.assertEqual(result["request_authenticated_approvals"],0)
        self.assertEqual(result["request_stage_writes"],0)
        self.assertFalse(result["request_is_execution_approval"])
    def test_request_without_review_ok_never_ready(self):
        rows,review,plan=data()
        rows[0]["Execution Request"]="REQUEST_STAGE_ONLY"
        rows[0]["Confirmation Phrase"]=CONFIRMATION
        rows[0]["Requested By"]="synthetic_owner"
        rows[0]["Requested At UTC"]="2026-11-23T01:00:00Z"
        result=assess_requests(rows,review,plan,NOW)
        self.assertEqual(result["request_review_not_confirmed_count"],1)
    def test_stale_uid_amount_scope_or_status_detected(self):
        changes=(("Amount KRW",123456),("IMAP UID","999"),
                 ("UIDVALIDITY","202"),("Scope","CANONICAL"),
                 ("Authorization Status","AUTHORIZED"),
                 ("Original PDF Filename","other.pdf"))
        for name,value in changes:
            with self.subTest(field=name):
                rows,review,plan=data();rows[0][name]=value
                r=assess_requests(rows,review,plan,NOW)
                self.assertEqual(r["request_binding_conflict_count"],1)
    def test_missing_owner_or_confirmation_never_ready(self):
        for key,value in (("Confirmation Phrase","STAGE"),
                          ("Requested By","")):
            rows,review,plan=data()
            review[0]["Review Selection (NOT WRITE APPROVAL)"]="REVIEW_OK"
            rows[0].update({
                "Review Status":"REVIEW_OK",
                "Execution Request":"REQUEST_STAGE_ONLY",
                "Confirmation Phrase":CONFIRMATION,
                "Requested By":"synthetic_owner",
                "Requested At UTC":"2026-11-23T01:00:00Z"})
            rows[0][key]=value
            r=assess_requests(rows,review,plan,NOW)
            self.assertEqual(r["request_confirmation_missing_count"],1)
    def test_expired_future_and_naive_time_rejected(self):
        for time in ("2026-11-20T12:00:00Z","2026-11-23T03:00:00Z",
                     "2026-11-23 01:00:00"):
            rows,review,plan=data()
            review[0]["Review Selection (NOT WRITE APPROVAL)"]="REVIEW_OK"
            rows[0].update({
                "Review Status":"REVIEW_OK",
                "Execution Request":"REQUEST_STAGE_ONLY",
                "Confirmation Phrase":CONFIRMATION,
                "Requested By":"synthetic_owner",
                "Requested At UTC":time})
            r=assess_requests(rows,review,plan,NOW)
            self.assertEqual(r["request_expired_or_invalid_count"],1)
    def test_request_with_user_metadata_and_no_selection_is_blocked(self):
        rows,review,plan=data()
        rows[0]["Requested By"]="synthetic_owner"
        r=assess_requests(rows,review,plan,NOW)
        self.assertEqual(r["request_unexpected_metadata_count"],1)
    def test_duplicate_scope_and_invalid_selection_raise_or_hold(self):
        rows,review,plan=data()
        rows[0]["Invoice Number"]=rows[1]["Invoice Number"]
        with self.assertRaisesRegex(ValueError,"REQUEST_DUPLICATE_OR_INVALID_INVOICE"):
            assess_requests(rows,review,plan,NOW)
        rows,review,plan=data()
        rows[0]["Execution Request"]="AUTO_APPLY"
        self.assertEqual(assess_requests(rows,review,plan,NOW)["request_invalid_selection_count"],1)
    def test_header_exact(self):
        self.assertEqual(len(REQUEST_HEADER),14)
        self.assertEqual(REQUEST_TAB,"건별 Stage 승인 요청 (미실행)")

if __name__=="__main__":
    unittest.main()
