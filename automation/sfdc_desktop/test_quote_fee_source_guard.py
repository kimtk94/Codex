"""Synthetic fee/Product matching tests; no real Quote IDs or customer prices."""
import unittest

from quote_fee_source_guard import reconcile_quotation_fee

P1 = "a0A" + "1" * 12
P2 = "a0A" + "2" * 12
FOREIGN = "a0A" + "3" * 12


def parent(net="1000", custom="400", grand="1540"):
    return dict(currency="KRW", gst="10,KR-VAT", net=net,
                totalcustom=custom, grand=grand, active=True, approved=True)


def fee(product=P1, fee_amount="400", fee_type="SP Sample Shipping Fee", **kw):
    return dict(fee_type=fee_type, fee=fee_amount, fee_to_calculate=fee_amount,
                currency="KRW", quotation_product_id=product, **kw)


def check(rows=None, ids=None, p=None):
    return reconcile_quotation_fee(
        parent=parent() if p is None else p,
        fee_rows=[fee()] if rows is None else rows,
        quotation_product_ids=[P1] if ids is None else ids,
    )


class QuotationFeeNativeRelationshipTests(unittest.TestCase):
    def test_exact_fee_sum_and_product_membership(self):
        result = check()
        self.assertEqual(result["status"], "FEE_SUM_AND_PRODUCT_LINK_VERIFIED_PROCESS_RATE_HOLD")
        self.assertTrue(result["fee_sum_verified"])
        self.assertTrue(result["product_link_verified"])
        self.assertEqual(result["fee_type_counts"]["SP Sample Shipping Fee"], 1)
        self.assertFalse(result["process_price_approved"])
        self.assertFalse(result["fee_approved_for_new_quote"])

    def test_two_products_fee_only_references_specific_parent_product(self):
        result = check(ids=[P1, P2])
        self.assertTrue(result["product_link_verified"])
        self.assertEqual(result["verified_fee_count"], 1)

    def test_sample_return_fee_with_zero_process_net(self):
        r = check(rows=[fee(fee_type="Sample Return Fee")],
                  p=parent(net="0", custom="400", grand="440"))
        self.assertTrue(r["process_net_zero"])
        self.assertFalse(r["process_price_approved"])

    def test_multiple_fees_require_exact_sum(self):
        r = check(rows=[fee(fee_amount="100"), fee(product=P2, fee_amount="300",
                 fee_type="Sample Return Fee")], ids=[P1, P2])
        self.assertTrue(r["fee_sum_verified"])
        self.assertEqual(r["verified_fee_count"], 2)

    def test_fee_record_for_other_quote_cannot_be_matched(self):
        r = check(rows=[fee(product=FOREIGN)], ids=[P1, P2])
        self.assertEqual(r["status"], "HOLD_FEE_PRODUCT_NOT_IN_QUOTE")

    def test_missing_or_duplicate_product_inventory_is_rejected(self):
        self.assertEqual(check(ids=[])["status"], "HOLD_SAME_QUOTE_PRODUCT_SOURCE_MISSING")
        self.assertEqual(check(ids=[P1, P1])["status"], "HOLD_DUPLICATE_PRODUCT_SOURCE")

    def test_unknown_fee_type_never_classified_as_shipping(self):
        r = check(rows=[fee(fee_type="Unknown Additional Fee")])
        self.assertEqual(r["status"], "HOLD_UNKNOWN_FEE_TYPE")

    def test_sum_mismatch_is_not_overridden_by_total_formula(self):
        r = check(rows=[fee(fee_amount="300")])
        self.assertEqual(r["status"], "HOLD_QUOTE_FEE_SUBTOTAL_MISMATCH")

    def test_fee_calculation_amount_mismatch_is_blocked(self):
        bad = fee()
        bad["fee_to_calculate"] = "399"
        self.assertEqual(check(rows=[bad])["status"], "HOLD_FEE_AMOUNT_UNVERIFIED")

    def test_usd_vat_and_unapproved_parent_are_rejected(self):
        for change in ({"currency":"USD"}, {"gst":"0 (HK VAT)"}, {"approved":False}):
            with self.subTest(change=change):
                p=parent()
                p.update(change)
                self.assertFalse(check(p=p)["fee_sum_verified"])

    def test_zero_or_absent_fee_never_becomes_a_process_price(self):
        for amount in ("0", "-100", None, "NaN", True):
            with self.subTest(amount=amount):
                bad=fee()
                bad["fee"]=amount
                self.assertEqual(check(rows=[bad])["status"], "HOLD_FEE_AMOUNT_UNVERIFIED")

    def test_all_outputs_prohibit_remote_writes(self):
        for r in (check(), check(rows=[fee(product=FOREIGN)])):
            self.assertFalse(r["quote_save_permitted"])
            self.assertFalse(r["process_price_approved"])
            self.assertFalse(r["fee_approved_for_new_quote"])
            self.assertEqual(r["crm_writes"], 0)


if __name__ == "__main__":
    unittest.main()
