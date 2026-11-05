import unittest
from quote_product_reference_readonly import REQUIRED_CHECKS, reference_only_audit


def round_evidence(i):
    return {"round":i,"mode":"READ_ONLY","save_clicked":False,
            "status":"PASS","checks":{key:True for key in REQUIRED_CHECKS}}


class QuoteProductReferenceTests(unittest.TestCase):
    def test_three_readonly_passes_only_confirm_historical_reference(self):
        report=reference_only_audit([round_evidence(i) for i in (1,2,3)])
        self.assertEqual(report["status"],"HISTORICAL_QUOTE_PRODUCT_REFERENCE_VERIFIED")
        self.assertTrue(report["saved_line_and_process_display_confirmed"])
        for key in ("current_product_catalog_id_verified","current_pricebook_entry_id_verified",
                    "current_quote_price_verified","new_product_creation_permitted","crm_save_allowed"):
            self.assertFalse(report[key])

    def test_missing_round_is_hold(self):
        self.assertEqual(reference_only_audit([round_evidence(1),round_evidence(2)])["historical_readback_rounds"],0)

    def test_two_duplicates_not_three_independent_rounds(self):
        r=[round_evidence(i) for i in (1,1,2)]
        self.assertEqual(reference_only_audit(r)["historical_readback_rounds"],0)

    def test_one_failed_price_reference_flag_blocks_reference_only(self):
        r=[round_evidence(i) for i in (1,2,3)]
        r[1]["checks"]["saved_list_price_krw_217500"]=False
        self.assertEqual(reference_only_audit(r)["status"],"HOLD_HISTORICAL_PRODUCT_READBACK_UNCONFIRMED")

    def test_missing_catalog_process_flag_blocks(self):
        r=[round_evidence(i) for i in (1,2,3)]
        del r[2]["checks"]["process_AliCloud"]
        self.assertEqual(reference_only_audit(r)["status"],"HOLD_HISTORICAL_PRODUCT_READBACK_UNCONFIRMED")

    def test_extra_unapproved_attribute_blocks(self):
        r=[round_evidence(i) for i in (1,2,3)]
        r[0]["checks"]["approved_new_price"]=True
        self.assertEqual(reference_only_audit(r)["historical_readback_rounds"],0)

    def test_save_attempt_never_validated_as_readonly(self):
        r=[round_evidence(i) for i in (1,2,3)]
        r[0]["save_clicked"]=True
        self.assertFalse(reference_only_audit(r)["saved_line_and_process_display_confirmed"])

    def test_three_runs_deterministic(self):
        values=[reference_only_audit([round_evidence(i) for i in (1,2,3)]) for _ in range(3)]
        self.assertEqual(values[0],values[1])
        self.assertEqual(values[1],values[2])

    def test_invalid_source_type(self):
        with self.assertRaises(ValueError):
            reference_only_audit(None)


if __name__=="__main__":
    unittest.main()
