import unittest
from invoice_gap_review import review, summary

class InvoiceGapTests(unittest.TestCase):
    def fixture(self):
        qq=[["invoice_number","issued_month","amount_krw","evidence"],
            ["209126000001","2026-10","1100","FILENAME_PARSED"],
            ["209126000002","2026-10","2200","FILENAME_PARSED"],
            ["209126000003","2026-09","550","FILENAME_PARSED"],
            ["209126000004","2026-10","3300","FILENAME_PARSED"]]
        css=[["invoice_number","invoice_month","amount_krw"],
             ["209126000004","2026-10","3300"],
             ["209125000999","2025-10","1100"]]
        extract=[["invoice_number","amount_krw","validation_status"],
                 ["209126000001","1100","FILENAME_PARSED"]]
        return qq,css,extract

    def test_gap_classification_does_not_authorize_revenue(self):
        rows=review(*self.fixture())
        stats=summary(rows)
        self.assertEqual(len(rows),3)
        self.assertEqual(stats["gross_krw_vat_included"],3850)
        self.assertEqual(stats["by_class"]["CSS_EXTRACT_PRESENT_CANONICAL_MISSING"],1)
        self.assertEqual(stats["by_class"]["QQ_ONLY_CSS_EXTRACT_MISSING"],2)
        self.assertTrue(all(r[8]=="NOT_VERIFIED" and r[9]=="DO_NOT_AUTO_ADD" for r in rows))

    def test_original_amount_conflict_blocks(self):
        qq,css,extract=self.fixture()
        extract[1][1]="999"
        with self.assertRaisesRegex(ValueError,"EXTRACT_AMOUNT_CONFLICT"):
            review(qq,css,extract)

    def test_duplicate_conflict_blocks(self):
        qq,css,extract=self.fixture()
        qq.append(["209126000001","2026-10","9999","FILENAME_PARSED"])
        with self.assertRaisesRegex(ValueError,"CONFLICTING_INVOICE_AMOUNT"):
            review(qq,css,extract)

    def test_canonical_only_2026_is_not_added_automatically(self):
        qq,css,extract=self.fixture()
        css.append(["209126000005","2026-10","7700"])
        result=review(qq,css,extract)
        self.assertEqual(result[-1][7],"CSS_CANONICAL_ONLY_QQ_MISSING")
        self.assertEqual(result[-1][9],"DO_NOT_AUTO_ADD")

if __name__=="__main__":
    unittest.main()
