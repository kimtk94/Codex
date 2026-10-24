import unittest
from automation.css_mail.qq_2025_bi_sync import normalize

HEADER = ["invoice_number", "issued_month", "amount_krw"]

class QQ2025MirrorTests(unittest.TestCase):
    def make_row(self, inv="209125000330", amt="5962000", evidence="CSS_TAX_INVOICE_LIST_VERIFIED_LEGACY"):
        return [inv,"2025-12",amt,"AMEA2025122219","H209SC251211206","SQ","INBOX","13274",
                "TAX INVOICE.pdf",evidence,"2026-10-24"]

    def test_verified_legacy(self):
        rows = normalize([HEADER, self.make_row()])
        self.assertEqual(rows["209125000330"][2], 5962000)
        self.assertEqual(rows["209125000330"][1], "2025-12")

    def test_2026_excluded(self):
        with self.assertRaises(ValueError):
            normalize([HEADER, self.make_row(inv="209126000330")])

    def test_conflicting_duplicate(self):
        with self.assertRaises(ValueError):
            normalize([HEADER, self.make_row(), self.make_row(amt="5963000")])

    def test_unverified_rejected(self):
        with self.assertRaises(ValueError):
            normalize([HEADER, self.make_row(evidence="INFERRED_FROM_QUOTE")])

if __name__ == "__main__":
    unittest.main()
