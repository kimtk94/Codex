"""Synthetic fixtures only: no real customers, QIDs, IDs or Quote prices."""
import unittest

from quote_custom_fee_guard import reconcile_native_krw_quote


def check(net, custom, grand, **override):
    sample = dict(currency="KRW", gst="10,KR-VAT", net=net,
                  totalcustom=custom, grand=grand, active=True, approved=True)
    sample.update(override)
    return reconcile_native_krw_quote(**sample)


class NativeKrwCustomFeeTests(unittest.TestCase):
    def test_custom_fee_exactly_explains_shared_957k_gross_gap(self):
        for net, gross in (("7740000", "9471000"),
                           ("11825000", "13964500"),
                           ("7955000", "9707500")):
            with self.subTest(net=net):
                result = check(net, "870000", gross)
                self.assertTrue(result["total_matched"])
                self.assertTrue(result["custom_fee_present"])
                self.assertEqual(result["status"], "HOLD_CUSTOM_FEE_PROCESS_UNALLOCATED")
                self.assertFalse(result["process_price_approved"])

    def test_custom_only_zero_process_net_not_promoted(self):
        for custom, gross in (("750000", "825000"), ("700000", "770000")):
            r = check("0", custom, gross)
            self.assertTrue(r["total_matched"])
            self.assertEqual(r["status"], "HOLD_CUSTOM_ONLY_ZERO_PROCESS_NET")
            self.assertFalse(r["quote_save_permitted"])

    def test_unexplained_grand_total_still_hold(self):
        self.assertEqual(check("100000", "20000", "133000")["status"],
                         "HOLD_TOTAL_STILL_MISMATCHED")

    def test_native_price_only_still_requires_original_process_readback(self):
        r = check("100000", "0", "110000")
        self.assertEqual(r["status"], "TOTAL_MATCHED_PROCESS_READBACK_REQUIRED")
        self.assertFalse(r["process_price_approved"])

    def test_usd_cannot_convert_to_krw(self):
        self.assertEqual(check("100", "0", "100", currency="USD")["status"],
                         "EXCLUDE_NON_KRW")

    def test_unsupported_gst_or_unapproved_blocks(self):
        self.assertEqual(check("100", "0", "110", gst="0 (HK VAT)")["status"],
                         "HOLD_NATIVE_KR_VAT_UNVERIFIED")
        self.assertEqual(check("100", "0", "110", approved=False)["status"],
                         "HOLD_INACTIVE_OR_UNAPPROVED")

    def test_missing_or_invalid_native_amount_fails_closed(self):
        for invalid in (None, "-1", "NaN", "Infinity", True, "100,000"):
            with self.subTest(invalid=invalid):
                r = check("1000", invalid, "1100")
                self.assertEqual(r["status"], "HOLD_INVALID_NATIVE_AMOUNTS")
                self.assertFalse(r["total_matched"])

    def test_no_test_case_can_authorize_salesforce_write(self):
        for item in (check("1000", "0", "1100"), check("0", "1000", "1100"),
                     check("1000", "100", "1210")):
            self.assertFalse(item["quote_save_permitted"])
            self.assertFalse(item["process_price_approved"])
            self.assertEqual(item["crm_writes"], 0)


if __name__ == "__main__":
    unittest.main()
