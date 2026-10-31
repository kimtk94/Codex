"""Fail-closed offline tests for generated source freshness exception review."""
import datetime as dt
import unittest
from css_evidence_exception_review import analyze,summary,HEAD,KST

NOW=dt.datetime(2026,10,31,14,30,tzinfo=KST)

def data():
    g=["209126000757","209126000788"]
    gap=[["Invoice Number","Issue Month","Gross KRW (VAT incl)"]]+[
        [num,"UNKNOWN",str(amount),"","","","","","NOT_VERIFIED","DO_NOT_AUTO_ADD",
         "2026-10-31 14:00:00 KST",""] for num,amount in zip(g,[2678500,5923500])]
    owner=[["Invoice No","QQ Month","Gross KRW (VAT incl)"]]+[
        [num,"",str(amount),"","","","","",
         "EXACT_AMOUNT_CANDIDATE" if num==g[0] else "NO_EXACT_RECEIPT_EVIDENCE",
         "1","MATCH","","","","NOT_VERIFIED","NOT_VERIFIED","DO_NOT_AUTO_ADD",
         "2026-10-31 14:00:00 KST",""] for num,amount in zip(g,[2678500,5923500])]
    return {
      "net":[["Month","Issued Invoice Gross KRW (VAT incl)",
             "Issued Net Revenue KRW (VAT excl)","","Issued Invoice Count","","","",
             "Evidence State"],
             ["2026-10","158541900","144129000","96.086","48","0",
              "21152370","2026-10-31 14:00:00 KST",
              "INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"]],
      "legacy":[["TAX INVOICE COMPLETENESS AUDIT","Value","Interpretation"],
                ["October invoice count","24",""],["October invoice amount KRW","56633500",""],
                ["Invoice source last date","2026-10-19",""]],
      "feishu":[["Source","Source Date","Synced At KST","Source ID","Rows","Schema"],
                ["Payment Outstanding","2026-10-26","2026-10-31 10:00:00 KST","","296","HEADER_MATCHED"],
                ["eTax Invoice","2026-10-26","2026-10-31 10:00:00 KST","","106","HEADER_MATCHED"],
                ["Payment Receipt","2026-10-26","2026-10-31 10:00:00 KST","","485","HEADER_MATCHED"],
                ["Prepayments","2026-10-26","2026-10-31 10:00:00 KST","","148","HEADER_MATCHED"],
                ["Online-Project","2026-10-31","2026-10-31 10:00:00 KST","","110","BASE_FIELDS"]],
      "gap":gap,"owner":owner,
      "accept":[["Area","Check","Result","Gate","Evidence KST","Observed","Next action","Checked KST"],
                ["SFDC","Three subscription Reports","WARN","DATA","","","","2026-10-31 11:20:20 KST"],
                ["Release","Owner-authenticated Preview E2E","BLOCK","RELEASE","","","","2026-10-31 11:20:20 KST"],
                ["Release","Production READY SHA parity","BLOCK","RELEASE","","","","2026-10-31 11:20:20 KST"],
                ["Decision","Production acceptance","BLOCK","RELEASE","","","","2026-10-31 11:20:20 KST"]],
      "mail":[["Updated At KST","State","QQ Staged Headers","Web Cached UID",
                "Body Ready","Body Empty MIME","Header Pending","Remaining Eligible",
                "Batch Selected","Batch Body Fetched","Batch Empty MIME","Fetch Errors"],
              ["2026-10-31 11:16:21 KST","WINDOW_CAUGHT_UP","7927","3912",
               "3660","249","0","0","0","0","0","0"]],
    }

class SourceEvidenceTests(unittest.TestCase):
    def test_real_shape_holds_legacy_and_payment_without_false_fail_job(self):
        rows=analyze(data(),NOW)
        self.assertEqual(len(rows),10)
        labels={r[1]:r for r in rows}
        self.assertEqual(labels["Canonical VAT-exclusive issued"][2],"PASS")
        self.assertEqual(labels["Legacy October coverage parity"][2],"REVIEW")
        self.assertIn("legacy_count=24;canonical_count=48",labels["Legacy October coverage parity"][5])
        self.assertEqual(labels["Legacy invoice source recency"][2],"REVIEW")
        self.assertEqual(labels["Payment source effective date"][2],"REVIEW")
        self.assertEqual(labels["Project status original date"][2],"PASS")
        self.assertEqual(labels["Canonical gap and owner hold"][2],"REVIEW")
        self.assertEqual(labels["Receipt candidate versus paid certification"][2],"REVIEW")
        self.assertEqual(labels["Production/owner browser release gate"][2],"REVIEW")
        self.assertEqual(labels["3-report source acceptance snapshot"][2],"REVIEW")
        self.assertEqual(labels["60-day body cache completion"][2],"PASS")
        self.assertEqual(summary(rows)["revenue_or_customer_writes"],0)
        self.assertEqual(len(HEAD),10)

    def test_canonical_net_vat_mismatch_is_explicit_block_not_different_scope(self):
        d=data()
        d["net"][1][2]="144128999"
        rows=analyze(d,NOW)
        self.assertEqual(rows[0][2],"BLOCK")

    def test_missing_owner_invoice_or_unapproved_revenue_is_fail_closed(self):
        d=data();d["owner"].pop()
        with self.assertRaisesRegex(ValueError,"GAP_OWNER_KEYS_DIFFER"):
            analyze(d,NOW)
        d=data();d["gap"][1][9]="AUTO_ADD"
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_INVOICE_REVENUE_CHANGE"):
            analyze(d,NOW)

    def test_missing_feishu_source_header_fails(self):
        d=data();d["feishu"][0][0]="Incorrect"
        with self.assertRaisesRegex(ValueError,"SOURCE_SCHEMA_FEISHU"):
            analyze(d,NOW)

    def test_old_canonical_timestamp_blocks_freshness(self):
        d=data();d["net"][1][7]="2026-10-30 12:00:00 KST"
        self.assertEqual(analyze(d,NOW)[0][2],"BLOCK")

    def test_cannot_infer_paid_from_receipt_candidate(self):
        d=data()
        d["owner"][1][8]="EXACT_AMOUNT_CANDIDATE"
        rows=analyze(d,NOW)
        r=next(r for r in rows if r[1]=="Receipt candidate versus paid certification")
        self.assertEqual(r[2],"REVIEW")
        self.assertIn("paid_certified=0",r[5])

    def test_reject_naive_clock_and_missing_release_gate(self):
        with self.assertRaisesRegex(ValueError,"NAIVE_NOW"):
            analyze(data(),dt.datetime(2026,10,31,14,30))
        d=data();d["accept"].pop()
        with self.assertRaisesRegex(ValueError,"RELEASE_GATE_MISSING"):
            analyze(d,NOW)

if __name__=="__main__":
    unittest.main()
