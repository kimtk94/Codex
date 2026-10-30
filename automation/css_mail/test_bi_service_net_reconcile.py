"""Offline source, VAT, and formula-summary integrity regression tests."""
import unittest
from bi_service_reconcile import invoice_net, source_parity, verify_summary, plan_new_review_rows

BASE=["Invoice No"]+[""]*12+["Net Revenue KRW (VAT excl; per invoice)"]
FACT=["Invoice Number"]+[""]*9+["Net Revenue KRW (VAT excl)","Net Revenue K USD (VAT excl)"]

def fixtures():
    original=["209126000965","2026-10","","198000"]+[""]*8+["0.12","180000"]
    processed=["209126000965","2026-10","Yonsei Univ.","Review / Other",
               "mRNA-seq","198000","0.132","SOURCE_NEW_REVIEW_2026-10-30",
               "AMEA2026081128","","180000","0.12"]
    return [BASE,original],[FACT,processed]

class NetReconciliationTests(unittest.TestCase):
    def test_invoice_net_uses_per_invoice_vat_conversion(self):
        self.assertEqual(invoice_net("4,438,500"),4035000)
        self.assertEqual(invoice_net("198000"),180000)
        self.assertEqual(invoice_net("9009000"),8190000)

    def test_verified_exact_source_and_fact_pass(self):
        base,fact=fixtures()
        out=source_parity(base,fact)
        self.assertEqual(list(out),["209126000965"])
        self.assertEqual(out["209126000965"][:2],(198000,180000))

    def test_new_unstaged_invoice_must_not_silently_disappear(self):
        base,fact=fixtures()
        base.append(["209126000968","2026-10","","9009000"]+[""]*8+["5.46","8190000"])
        with self.assertRaisesRegex(RuntimeError,"SOURCE_INVOICE_NOT_IN_FACT"):
            source_parity(base,fact)

    def test_reject_gross_net_and_original_formula_mismatch(self):
        base,fact=fixtures()
        fact[1][10]="198000"
        with self.assertRaisesRegex(RuntimeError,"FACT_INVOICE_NET_OR_GROSS_MISMATCH"):
            source_parity(base,fact)
        base,fact=fixtures()
        base[1][13]="198000"
        with self.assertRaisesRegex(RuntimeError,"BASE_NET_AMOUNT_MISMATCH"):
            source_parity(base,fact)

    def test_auto_imports_new_verified_original_only_as_unapproved_review(self):
        base,fact=fixtures()
        source=["209126000968","2026-10","2026-10-19","9009000",
                "Jeju Univ.","mRNA-Seq","NGS","AMEA2026091421","","","mRNA-seq","","6.006","8190000"]
        base.append(source)
        new=plan_new_review_rows(base,fact,1500,"2026-10-30")
        self.assertEqual(new,[
            ["209126000968","2026-10","Jeju Univ.","Review / Other",
             "mRNA-seq",9009000,6.006,"SOURCE_NEW_REVIEW_2026-10-30",
             "AMEA2026091421",""]])
        self.assertEqual(fact[1][3],"Review / Other")
        self.assertEqual(base[2][3],"9009000")

    def test_auto_import_is_idempotent_after_calculated_net_is_available(self):
        base,fact=fixtures()
        self.assertEqual(plan_new_review_rows(base,fact,1500,"2026-10-30"),[])

    def test_missing_amea_or_l4_never_creates_synthetic_invoice(self):
        base,fact=fixtures()
        extra=["209126000968","2026-10","2026-10-19","9009000",
               "Jeju Univ.","mRNA-Seq","NGS","","","","mRNA-seq","","6.006","8190000"]
        base.append(extra)
        with self.assertRaisesRegex(RuntimeError,"SOURCE_INVOICE_METADATA_INCOMPLETE"):
            plan_new_review_rows(base,fact,1500,"2026-10-30")

    def test_bad_existing_gross_blocks_append_without_mutation(self):
        base,fact=fixtures()
        fact[1][5]="190000"
        with self.assertRaisesRegex(RuntimeError,"FACT_INVOICE_NET_OR_GROSS_MISMATCH"):
            plan_new_review_rows(base,fact,1500,"2026-10-30")

    def test_summary_verification_preserves_formulas_and_fails_closed(self):
        summary=[["Service Group","Invoice Count","Net Revenue KRW (VAT excl)","Net Revenue K USD (VAT excl)"],
                 ["Review / Other","2","8370000","5.58"]]
        verify_summary(summary,[["Review / Other",2,8370000,5.58]])
        summary[1][2]="9207000"
        with self.assertRaisesRegex(RuntimeError,"SUMMARY_NET_AMOUNT_MISMATCH"):
            verify_summary(summary,[["Review / Other",2,8370000,5.58]])

if __name__=="__main__":
    unittest.main()
