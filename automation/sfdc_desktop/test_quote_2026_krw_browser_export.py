"""Synthetic-only tests: Salesforce browser is never contacted."""
import unittest
from decimal import Decimal
from quote_2026_krw_browser_export import amount,next_field,money_after,native_lookup,extract

class NeverNavigate:
    def goto(self,*args,**kwargs):
        raise AssertionError("CRM_NAVIGATION_MUST_NOT_HAPPEN")

class SfdcKrwReadbackTests(unittest.TestCase):
    def test_krw_amount_and_no_usd_or_negative(self):
        self.assertEqual(amount("4,275,000.00"),Decimal("4275000.00"))
        self.assertEqual(amount("0"),Decimal("0"))
        for bad in ["USD 12","-100","$100","0.001 USD","bad",""]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):amount(bad)

    def test_quote_total_and_tax_extract_are_native_krw(self):
        sample="Total Price\nKRW 4,275,000.00\nGrand Total\nKRW 4,702,500.00\n"
        self.assertEqual(money_after(sample,"Total Price"),Decimal("4275000.00"))
        self.assertEqual(money_after(sample,"Grand Total"),Decimal("4702500.00"))
        with self.assertRaises(ValueError):money_after(sample.replace("KRW","USD"),"Total Price")

    def test_native_lookup_never_uses_cp_external_contact(self):
        ids=["/lightning/r/Account/001000000000AAA/view",
             "/lightning/r/Contact/003000000000AAB/view"]
        self.assertEqual(native_lookup(ids,"Account"),"001000000000AAA")
        self.assertEqual(native_lookup(ids,"Contact"),"003000000000AAB")
        with self.assertRaises(ValueError):native_lookup(["/lightning/r/Contact/CP20260000000/view"],"Contact")
        with self.assertRaises(ValueError):native_lookup([
            "/lightning/r/Account/001000000000AAA/view",
            "/lightning/r/Account/001000000000AAB/view"],"Account")

    def test_missing_approval_and_process_map_block_before_any_navigation(self):
        base={"quote_id":"QID-2026-11-13-414294",
              "record_id":"a0P000000000AAA",
              "created_date":"2026-11-13",
              "amea_id":"AMEA2026111315",
              "approval_evidence":"MISSING",
              "process_ids":{"Library preparation":"Process-2020-04-29-00039"}}
        with self.assertRaisesRegex(ValueError,"APPROVAL_MANIFEST_INVALID"):
            extract(NeverNavigate(),base)
        valid={**base,"approval_evidence":"APPROVED_TEXT","process_ids":{}}
        with self.assertRaisesRegex(ValueError,"PROCESS_ID_MAP_MISSING"):
            extract(NeverNavigate(),valid)

    def test_next_field_does_not_guess_values(self):
        self.assertEqual(next_field(["Currency","KRW","Active","True"],"Currency"),"KRW")
        self.assertEqual(next_field(["Currency","KRW"],"Unit Price"),"")

if __name__=="__main__":
    unittest.main()
