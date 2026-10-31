"""Regression tests for exact-key sales evidence and receipt candidate boundaries."""
import unittest
from invoice_owner_payment_evidence import build,stats,HEAD

def fixture():
    gaps=[["Invoice Number","Issue Month","Gross KRW (VAT incl)"],
      ["209126000001","2026-10","1100"],
      ["209126000002","UNKNOWN","2200"],
      ["209126000003","2026-10","3300"]]
    qq=[["invoice_number","issued_month","amount_krw","amea_project_id","h_project_id"],
      ["209126000001","2026-10","1100","AMEA2026010101","H209SC26001001"],
      ["209126000002","","2200","AMEA2026010102","H209SC26001002"],
      ["209126000003","2026-10","3300","AMEA2026010103","H209SC26001003"]]
    out=[["CMS Invoice Number","Project Number","Sales","Invoice Amount"],
      ["209126000001","X209SC26001001","Kim Taehoon","1100"],
      ["209126000002","X209SC26001002","Other Sales","2200"]]
    tax=[["CMS Invoice Num","Project Number","Sales","Amount","Quotation Number"],
      ["209126000001","X209SC26001001","Kim Taehoon","1100","AMEA2026010101"]]
    receipts=[["CMS No.","Amount (KRW)","Deposit Date","CMS No. [2]",
        "Amount","Date","CMS No. [3]","Amount [2]","Date [2]"],
      ["209126000002","2200","10-Oct-26","","","","","",""]]
    manifest=[["Source","Source Date","Source ID","Schema"],
      ["Payment Outstanding","2026-10-26","src1","HEADER_MATCHED"],
      ["eTax Invoice","2026-10-26","src2","HEADER_MATCHED"],
      ["Payment Receipt","2026-10-26","src3","HEADER_MATCHED"]]
    return gaps,qq,out,tax,receipts,manifest

class InvoiceOwnerEvidenceTests(unittest.TestCase):
    def test_sales_self_other_and_receipt_exact_amount_are_only_candidates(self):
        rows=build(*fixture())
        self.assertEqual(3,len(rows))
        self.assertEqual(rows[0][6],"SELF_TAGGED_UNCONFIRMED")
        self.assertEqual(rows[1][6],"OTHER_TAGGED_REVIEW")
        self.assertEqual(rows[1][8],"EXACT_AMOUNT_CANDIDATE")
        self.assertEqual(rows[2][6],"NO_FEISHU_SALES_TAG")
        self.assertTrue(all(r[14]=="NOT_VERIFIED" and r[15]=="NOT_VERIFIED"
                            and r[16]=="DO_NOT_AUTO_ADD" for r in rows))
        self.assertEqual(len(HEAD),19)
        self.assertEqual(stats(rows)["owner_certified"],0)
        self.assertEqual(stats(rows)["paid_certified"],0)

    def test_feishu_contract_or_amount_conflict_blocks(self):
        args=list(fixture())
        args[2][1][1]="X209SC999"
        with self.assertRaisesRegex(ValueError,"FEISHU_CONTRACT_CONFLICT"):
            build(*args)
        args=list(fixture())
        args[2][1][3]="999"
        with self.assertRaisesRegex(ValueError,"FEISHU_GROSS_CONFLICT"):
            build(*args)

    def test_invalid_receipt_amount_only_review_not_paid(self):
        args=list(fixture())
        args[4][1][1]="1000"
        rows=build(*args)
        self.assertEqual(rows[1][8],"AMOUNT_CONFLICT_REVIEW")
        self.assertEqual(rows[1][15],"NOT_VERIFIED")

    def test_unvalidated_snapshot_fails_closed(self):
        args=list(fixture())
        args[5][1][3]="MISMATCH"
        with self.assertRaisesRegex(ValueError,"FEISHU_SNAPSHOT_NOT_VALIDATED"):
            build(*args)

    def test_tampered_original_invoice_amount_fails(self):
        args=list(fixture())
        args[1][1][2]="1111"
        with self.assertRaisesRegex(ValueError,"GAP_SOURCE_AMOUNT_DRIFT"):
            build(*args)

    def test_receipt_same_amount_wrong_number_is_not_a_match(self):
        args=list(fixture())
        args[4][1][0]="209126000099"
        rows=build(*args)
        self.assertEqual(rows[1][8],"NO_EXACT_RECEIPT_EVIDENCE")

if __name__=="__main__":
    unittest.main()
