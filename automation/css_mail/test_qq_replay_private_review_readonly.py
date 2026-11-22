"""All-local private review audit tests, never access Google Sheets."""
import json
import unittest
from automation.css_mail.qq_replay_private_review_readonly import (
    HEADER, _table, review_audit
)


def fixture():
    cid="1234567890"
    extract={"invoice_number":cid,"amount_krw":"1500","project_id":"P",
             "h_project_number":"H","po_reference":"PO","attachment_filename":"inv.pdf",
             "imap_uid":"100","validation_status":"FILENAME_PARSED",
             "extracted_at_utc":"2026-11-20T12:00:00+00:00",
             "ingest_key":"INBOX|201|100"}
    r={"No.":"1","Invoice Number":cid,"Amount KRW":1500,
       "Project ID":"P","H Project Number":"H","PO Reference":"PO",
       "Original PDF Filename":"inv.pdf","IMAP UID":"100",
       "UIDVALIDITY":"201","Evidence Status":"FILENAME_PARSED",
       "Extracted At UTC":"2026-11-20T12:00:00+00:00",
       "Current Status":"HOLD","Review Selection (NOT WRITE APPROVAL)":"HOLD",
       "Reviewer":"","Reviewed At":"","Review Notes":""}
    reviews=[]
    extracts=[]
    for i in range(7):
        rr=dict(r);ee=dict(extract)
        rr["No."]=str(i+1)
        rr["Invoice Number"]=str(int(cid)+i)
        ee["invoice_number"]=rr["Invoice Number"]
        ee["imap_uid"]=str(100+i)
        ee["ingest_key"]=f"INBOX|201|{100+i}"
        rr["IMAP UID"]=str(100+i)
        reviews.append(rr);extracts.append(ee)
    cursor=[{"year":"2026","folder":"INBOX","uidvalidity":"201","last_uid":"500"}]
    audit=[{"year":"2026","status":"SCAN_COMPLETE",
            "last_run_utc":"2026-11-22T00:00:00+00:00"}]
    return reviews,extracts,[],[],cursor,audit


class PrivateReviewTests(unittest.TestCase):
    def test_seven_holds_are_matched_and_never_approved(self):
        data=fixture()
        v=review_audit(*data)
        self.assertEqual(v["review_cases"],7)
        self.assertEqual(v["source_match_count"],7)
        self.assertEqual(v["review_hold_count"],7)
        self.assertEqual(v["authenticated_approvals"],0)
        self.assertEqual(v["stage_writes"],0)
        self.assertEqual(v["status"],"HOLD")
        self.assertNotIn("123456789",json.dumps(v))
    def test_all_review_ok_still_cannot_authorize(self):
        data=fixture()
        for r in data[0]:
            r["Review Selection (NOT WRITE APPROVAL)"]="REVIEW_OK"
        v=review_audit(*data)
        self.assertEqual(v["review_ok_count"],7)
        self.assertEqual(v["authenticated_approvals"],0)
        self.assertFalse(v["review_is_execution_approval"])
    def test_amount_uid_and_epoch_drift_counted(self):
        for field,val in (("Amount KRW",2000),("IMAP UID","404"),
                          ("UIDVALIDITY","202"),("Original PDF Filename","other.pdf")):
            data=fixture()
            data[0][0][field]=val
            v=review_audit(*data)
            self.assertEqual(v["source_match_count"],6)
            self.assertEqual(v["source_conflict_count"],1)
    def test_existing_sink_record_is_not_candidate(self):
        data=fixture()
        data[2].append({"invoice_number":data[0][0]["Invoice Number"]})
        v=review_audit(*data)
        self.assertEqual(v["source_conflict_count"],1)
    def test_changed_audit_status_fails_closed(self):
        data=list(fixture())
        data[5][0]["status"]="RUNNING"
        with self.assertRaisesRegex(ValueError,"REVIEW_CURSOR_OR_AUDIT_INVALID"):
            review_audit(*data)
    def test_duplicate_and_unknown_decision_fail_closed(self):
        data=fixture()
        data[0][1]["Invoice Number"]=data[0][0]["Invoice Number"]
        with self.assertRaisesRegex(ValueError,"REVIEW_DUPLICATE_OR_INVALID_INVOICE"):
            review_audit(*data)
        data=fixture()
        data[0][0]["Review Selection (NOT WRITE APPROVAL)"]="EXECUTE"
        with self.assertRaisesRegex(ValueError,"REVIEW_SELECTION_INVALID"):
            review_audit(*data)
    def test_strict_table_header_and_no_formula_interpretation(self):
        a=_table([HEADER]+[[str(i+1)]+["x"]*15 for i in range(7)],"review")
        self.assertEqual(len(a),7)
        with self.assertRaisesRegex(ValueError,"REVIEW_SCHEMA_CHANGED"):
            _table([list(reversed(HEADER))]+[["x"]*16],"review")


if __name__=="__main__":
    unittest.main()
