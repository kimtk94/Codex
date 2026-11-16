"""Synthetic scenarios for 2026 KRW original Quote HOLD classification. No CRM."""
import unittest
from decimal import Decimal
from quote_2026_krw_totals_guard import require_original_krw_totals


class NativeKrwHoldTests(unittest.TestCase):
    def test_valid_original_krw_vat10_accepts_exact_native_amounts(self):
        self.assertEqual(
            require_original_krw_totals("KRW","True","1200000","1320000","10(KR VAT)"),
            (Decimal("1200000"),Decimal("1320000")))
        self.assertEqual(require_original_krw_totals("KRW","True",
            Decimal("100.00"),Decimal("110.05"),"10"),(Decimal("100.00"),Decimal("110.05")))

    def test_zero_net_and_positive_gross_are_hold_even_if_vat_label_10(self):
        with self.assertRaisesRegex(ValueError,"QUOTE_VAT_TOTAL_MISMATCH"):
            require_original_krw_totals("KRW","True","0","770000","10(KR VAT)")
        with self.assertRaisesRegex(ValueError,"QUOTE_VAT_TOTAL_MISMATCH"):
            require_original_krw_totals("KRW","True","0","0","10(KR VAT)")

    def test_positive_native_net_but_inconsistent_grand_must_hold(self):
        for gross in ("1200000","0","1250000","1320000.06"):
            with self.subTest(gross=gross),self.assertRaisesRegex(ValueError,"QUOTE_VAT_TOTAL_MISMATCH"):
                require_original_krw_totals("KRW","True","1200000",gross,"10(KR VAT)")

    def test_non_krw_quote_with_hk_vat_cannot_be_converted(self):
        with self.assertRaisesRegex(ValueError,"NOT_NATIVE_KRW"):
            require_original_krw_totals("USD","True","100","100","0 (HK VAT)")

    def test_vat_setting_must_not_override_amounts_or_grant_exception(self):
        with self.assertRaisesRegex(ValueError,"QUOTE_VAT_SETTING_MISMATCH"):
            require_original_krw_totals("KRW","True","100","100","0 (HK VAT)")
        with self.assertRaisesRegex(ValueError,"QUOTE_VAT_TOTAL_MISMATCH"):
            require_original_krw_totals("KRW","True","100","100","10(KR VAT)")

    def test_inactive_and_invalid_source_are_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"NOT_ACTIVE"):
            require_original_krw_totals("KRW","False","100","110","10")
        for net,gross in (("NaN","110"),("Infinity","110"),("invalid","110"),
                          ("-10","-11"),("100","NaN")):
            with self.subTest(net=net,gross=gross),self.assertRaises(ValueError):
                require_original_krw_totals("KRW","True",net,gross,"10")


if __name__=="__main__":
    unittest.main()
