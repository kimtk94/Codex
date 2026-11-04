"""Synthetic tests: price field visibility is not price authorization."""
import unittest
from pathlib import Path

from inspect_pe250_quote_wizard_price_fields_no_save import pricing_field_presence


class Pe250UnsavedPriceFieldsTests(unittest.TestCase):
    def test_price_label_presence_does_not_approve_amount(self):
        found=pricing_field_presence("Unit Price: 100",["Sample Number","Data Size"])
        self.assertTrue(found["unit price"])
        self.assertTrue(found["price"])
        self.assertTrue(found["sample number"])

    def test_absent_price_labels_are_false(self):
        found=pricing_field_presence("Process List NovaSeq Reagent Kit",["Data Size"])
        for field in ("unit price","list price","sales price","pricebook","currency","discount"):
            if field in found:
                self.assertFalse(found[field])

    def test_casefold(self):
        found=pricing_field_presence("TOTAL AMOUNT",["CURRENCY","DATA SIZE"])
        self.assertTrue(found["total amount"])
        self.assertTrue(found["currency"])

    def test_no_persistent_save_action_in_diagnostic(self):
        source=(Path(__file__).parent/"inspect_pe250_quote_wizard_price_fields_no_save.py").read_text(encoding="utf-8")
        self.assertNotIn('name="Save"',source)
        self.assertNotIn('name="Done"',source)
        self.assertNotIn('name="Create"',source)
        self.assertNotIn('name="Pack"',source)
        self.assertIn('"save_clicked":False',source)

    def test_three_round_stable_detection(self):
        checks=[pricing_field_presence("Unit Price",["Data Size"]) for _ in range(3)]
        self.assertEqual(checks[0],checks[1])
        self.assertEqual(checks[1],checks[2])


if __name__=="__main__":
    unittest.main()
