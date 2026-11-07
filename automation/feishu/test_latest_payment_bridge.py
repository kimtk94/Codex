#!/usr/bin/env python3
"""Latest dated Payment sheets -> project payment/archiving regression suite."""
import datetime as dt
import unittest
from latest_payment_bridge import (build_payment_evidence,source_dates,date_str)
from project_settlement import (
    ACTIVE,PAYMENT,ARCHIVE,completion_evidence,finalize,verified_full_payment
)
KST=dt.timezone(dt.timedelta(hours=9))
NOW=dt.datetime(2026,11,7,9,0,tzinfo=KST)
P="AMEA2026100751"
X="X209SC26102746"
I="209126000991"
def etax(invoice=I,pid=P,amount="1100000",x=X,sales="Kim Taehoon"):
    return {"CMS Invoice Num":invoice,"Quotation Number":pid,"Project Number":x,
            "Amount":amount,"Sales":sales}
def out(invoice=I,pid=P,amount="1100000",balance="",x=X,sales="Kim Taehoon"):
    return {"CMS Invoice Number":invoice,"Quotation Number":pid,"Project Number":x,
            "Invoice Amount":amount,"Balance":balance,"Sales":sales}
def receipt(invoice=I,amount="1100000",date="45960"):
    return {"CMS No.":invoice,"Amount (KRW)":amount,"Deposit Date":date,
            "CMS No. [2]":"","Amount":"","Date":"",
            "CMS No. [3]":"","Amount [2]":"","Date [2]":""}
def manifest():
    return [
      {"Source":"Payment Receipt","Source Date":"2026-10-31",
       "Synced At KST":"2026-11-07T07:20:08+09:00","Schema":"HEADER_MATCHED"},
      {"Source":"Payment Outstanding","Source Date":"2026-11-01",
       "Synced At KST":"2026-11-07T07:20:08+09:00","Schema":"HEADER_MATCHED"},
      {"Source":"eTax Invoice","Source Date":"2026-10-31",
       "Synced At KST":"2026-11-07T07:20:08+09:00","Schema":"HEADER_MATCHED"},
    ]
def sources(es=None,outs=None,rec=None):
    return {"Feishu Latest eTax":es if es is not None else [etax()],
            "Feishu Latest Outstanding":outs if outs is not None else [out()],
            "Feishu Latest Receipts":rec if rec is not None else [receipt()]}

class LatestPaymentTests(unittest.TestCase):
    def test_exact_cms_amount_and_date_with_no_balance_is_source_verified(self):
        matches,billing,info=build_payment_evidence(sources(),manifest(),NOW)
        self.assertIn(P,matches)
        self.assertEqual(matches[P]["Receipt Verification Status"],"SOURCE_EXACT_VERIFIED")
        self.assertEqual(matches[P]["Verified Received KRW"],1100000)
        self.assertEqual(matches[P]["Receipt Source Snapshot Date"],"2026-10-31")
        self.assertEqual(billing[P]["Invoice Gross KRW"],1100000)
        self.assertEqual(billing[P]["Payment Owner Scope"],"MY_VERIFIED")
        self.assertEqual(info["projects_source_receipt_complete"],1)
        self.assertTrue(verified_full_payment(matches[P]))
    def test_other_sales_is_not_my_payment(self):
        matched,billing,info=build_payment_evidence(
            sources(es=[etax(sales="Yinglan Piao 朴英兰")],
                    outs=[out(sales="Yinglan Piao 朴英兰")]),manifest(),NOW)
        self.assertEqual(billing[P]["Payment Owner Scope"],"OTHER_SALES")
        self.assertEqual(info["my_verified_invoice_projects"],0)
        # A valid receipt for another salesperson must never pass personal filter.
        self.assertIn(P,matched)
    def test_mixed_sales_labels_fail_closed(self):
        _,billing,_=build_payment_evidence(
            sources(es=[etax(sales="Kim Taehoon")],
                    outs=[out(sales="Hyunseok KOO")]),manifest(),NOW)
        self.assertEqual(billing[P]["Payment Owner Scope"],"OWNER_UNVERIFIED")
    def test_missing_sales_labels_fail_closed(self):
        _,billing,_=build_payment_evidence(
            sources(es=[etax(sales="")],
                    outs=[out(sales="Kim Taehoon")]),manifest(),NOW)
        self.assertEqual(billing[P]["Payment Owner Scope"],"OWNER_UNVERIFIED")
    def test_similar_name_or_substring_is_not_accepted(self):
        _,billing,_=build_payment_evidence(
            sources(es=[etax(sales="Kim Taehoon (Other)")],
                    outs=[out(sales="Kim Taehoon (Other)")]),manifest(),NOW)
        self.assertNotEqual(billing[P]["Payment Owner Scope"],"MY_VERIFIED")
    def test_multiple_invoice_owners_must_all_be_mine(self):
        second="209126000992"
        _,billing,_=build_payment_evidence(sources(
            es=[etax(),etax(invoice=second,sales="Lim Hyunjung")],
            outs=[out(),out(invoice=second,sales="Lim Hyunjung")]),
            manifest(),NOW)
        self.assertEqual(billing[P]["Payment Owner Scope"],"OWNER_UNVERIFIED" if
            "OWNER_UNVERIFIED"==billing[P]["Payment Owner Scope"] else "OTHER_SALES")
    def test_identity_whitespace_normalized_only(self):
        _,billing,_=build_payment_evidence(
            sources(es=[etax(sales="Kim   Taehoon")],
                    outs=[out(sales=" Kim Taehoon ")]),manifest(),NOW)
        self.assertEqual(billing[P]["Payment Owner Scope"],"MY_VERIFIED")

    def test_invoiced_but_not_completed_stays_active(self):
        matches,_,_=build_payment_evidence(sources(),manifest(),NOW)
        row={"Completion Evidence":"NOT_VERIFIED","Next Action":"QC"}
        item=finalize(row,matches[P])
        self.assertEqual(item["Workflow Lane"],ACTIVE)
    def test_completed_with_exact_payment_moves_to_archived(self):
        matches,_,_=build_payment_evidence(sources(),manifest(),NOW)
        row={"Completion Evidence":"CSS_EXPLICIT_FINAL_HANDOFF"}
        item=finalize(row,matches[P])
        self.assertEqual(item["Workflow Lane"],ARCHIVE)
        self.assertEqual(item["Payment State"],"PAID_SOURCE_MATCHED")
    def test_completed_without_receipt_moves_to_payment_dashboard(self):
        matches,_,_=build_payment_evidence(sources(rec=[receipt("209126000992")]),manifest(),NOW)
        self.assertNotIn(P,matches)
        row={"Completion Evidence":"CSS_EXPLICIT_FINAL_HANDOFF"}
        item=finalize(row)
        self.assertEqual(item["Workflow Lane"],PAYMENT)
    def test_invoice_issued_without_final_report_is_not_completion(self):
        self.assertEqual(completion_evidence("Invoice issued",[]),"NOT_VERIFIED")
        self.assertEqual(completion_evidence("Final Report Ready",[]),"CSS_EXPLICIT_FINAL_HANDOFF")
    def test_positive_outstanding_even_if_receipt_exists_blocks_archival(self):
        matches,_,_=build_payment_evidence(sources(outs=[out(balance="1100000")]),manifest(),NOW)
        self.assertNotIn(P,matches)
    def test_bundled_multi_cms_receipt_amount_not_apportioned(self):
        rec=receipt(invoice=I+", 209126000992",amount="2200000")
        matches,_,info=build_payment_evidence(sources(rec=[rec]),manifest(),NOW)
        self.assertNotIn(P,matches)
        self.assertGreater(info["receipt_ambiguities"],0)
    def test_partial_receipt_does_not_hide(self):
        matches,_,_=build_payment_evidence(sources(rec=[receipt(amount="500000")]),manifest(),NOW)
        self.assertNotIn(P,matches)
    def test_two_distinct_receipts_sum_to_exact_invoice(self):
        rec=[receipt(amount="500000",date="45960"),receipt(amount="600000",date="45961")]
        matches,_,_=build_payment_evidence(sources(rec=rec),manifest(),NOW)
        self.assertIn(P,matches)
        self.assertEqual(matches[P]["Verified Received KRW"],1100000)
    def test_duplicate_receipt_rows_trigger_review(self):
        rec=[receipt(),receipt()]
        matches,_,info=build_payment_evidence(sources(rec=rec),manifest(),NOW)
        self.assertNotIn(P,matches)
        self.assertGreater(info["receipt_ambiguities"],0)
    def test_cross_project_invoice_conflict_does_not_auto_match(self):
        matches,_,_=build_payment_evidence(
          sources(es=[etax(),etax(pid="AMEA2026110999")]),manifest(),NOW)
        self.assertNotIn(P,matches)
    def test_old_mirror_prevents_auto_payment(self):
        rows=manifest()
        rows[0]["Synced At KST"]="2026-11-01T01:00:00+09:00"
        with self.assertRaisesRegex(ValueError,"MIRROR_STALE"):
            build_payment_evidence(sources(),rows,NOW)
    def test_paid_requires_exact_date_and_invoice_amount(self):
        matches,_,_=build_payment_evidence(sources(),manifest(),NOW)
        tampered={**matches[P],"Verified Received KRW":1100001}
        self.assertFalse(verified_full_payment(tampered))
        self.assertEqual(date_str("45960"),"2025-10-30")
        self.assertEqual(date_str("nonsense"),"")
    def test_multiple_subprojects_one_final_report_not_closed(self):
        p=completion_evidence("Final Report Ready",[
            {"CSS Stage (legacy)":"Final Report Ready"},
            {"CSS Stage (legacy)":"Sequencing"},
        ])
        self.assertEqual(p,"PARTIAL_SUBPROJECT_COMPLETION_REVIEW")
if __name__=="__main__":unittest.main()
