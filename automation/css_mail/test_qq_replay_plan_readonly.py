"""Source-backed, synthetic-only recovery row plan fail-closed tests."""
import json
import unittest
from automation.css_mail.qq_replay_plan_readonly import validate_plan,PLAN_HEADER
from automation.css_mail.test_qq_replay_private_review_readonly import fixture

def sample():
    r,e,s,c,_,_=fixture()
    p=[]
    for x in e:
        p.append({
            "invoice_number":x["invoice_number"],"issued_month":"",
            "amount_krw":int(x["amount_krw"]),
            "amea_project_id":x["project_id"],
            "h_project_id":x["h_project_number"],
            "po_reference":x["po_reference"],
            "imap_folder":"INBOX","imap_uid":x["imap_uid"],
            "filename":x["attachment_filename"],
            "evidence":x["validation_status"],"backfill_utc":""})
    return p,r,e,s,c

class PlanTests(unittest.TestCase):
    def test_matching_seven_are_never_authorized(self):
        result=validate_plan(*sample())
        self.assertEqual(result["plan_source_match_count"],7)
        for f in ("plan_authenticated_approvals","plan_actual_stage_writes",
                  "plan_cursor_writes","plan_canonical_writes",
                  "plan_writer_exclusion_verified"):
            self.assertEqual(result[f],0)
        self.assertEqual(result["plan_status"],"HOLD")
        self.assertNotIn("123456789",json.dumps(result))
    def test_blank_month_and_execution_time_mandatory(self):
        for k,v in (("issued_month","2026-11"),("backfill_utc","now")):
            d=sample();d[0][0][k]=v
            self.assertEqual(validate_plan(*d)["plan_invented_month_or_time_count"],1)
    def test_changes_to_all_fields_block_exact_match(self):
        for k,v,reason in (
            ("amount_krw",5000,"plan_amount_mismatch_count"),
            ("filename","other.pdf","plan_identity_mismatch_count"),
            ("imap_uid","999","plan_identity_mismatch_count"),
            ("imap_folder","SENT","plan_identity_mismatch_count"),
            ("evidence","OTHER","plan_identity_mismatch_count"),
            ("amea_project_id","changed","plan_identity_mismatch_count"),
            ("h_project_id","changed","plan_identity_mismatch_count"),
            ("po_reference","changed","plan_identity_mismatch_count"),
        ):
            with self.subTest(k=k):
                d=sample();d[0][0][k]=v
                self.assertEqual(validate_plan(*d)[reason],1)
    def test_existing_sink_blocks(self):
        for sink_index in (3,4):
            d=sample();d[sink_index].append({"invoice_number":d[0][0]["invoice_number"]})
            self.assertEqual(validate_plan(*d)["plan_existing_sink_count"],1)
    def test_duplicate_or_missing_row_fails(self):
        d=sample();d[0][0]["invoice_number"]=d[0][1]["invoice_number"]
        with self.assertRaisesRegex(ValueError,"PLAN_DUPLICATE_OR_INVALID_INVOICE"):
            validate_plan(*d)
        d=sample();d[0].pop()
        with self.assertRaisesRegex(ValueError,"PLAN_SEVEN_ROWS_REQUIRED"):
            validate_plan(*d)
    def test_review_ok_remains_non_authoritative(self):
        d=sample()
        for r in d[1]:r["Review Selection (NOT WRITE APPROVAL)"]="REVIEW_OK"
        out=validate_plan(*d)
        self.assertEqual(out["plan_source_match_count"],7)
        self.assertEqual(out["plan_authenticated_approvals"],0)
    def test_original_changed_is_detected(self):
        d=sample();d[2][0]["amount_krw"]="8888"
        # A changed source amount first conflicts with the independently
        # captured review row. That earlier HOLD classification is stronger.
        report=validate_plan(*d)
        self.assertEqual(report["plan_review_mismatch_count"],1)
        self.assertEqual(report["plan_source_match_count"],6)
    def test_header_exact_schema(self):
        self.assertEqual(len(PLAN_HEADER),11)
        self.assertEqual(PLAN_HEADER[1],"issued_month")
        self.assertEqual(PLAN_HEADER[-1],"backfill_utc")

if __name__=="__main__":
    unittest.main()
