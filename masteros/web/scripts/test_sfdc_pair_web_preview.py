import unittest
from unittest.mock import patch

from sfdc_pair_web_preview import run,validate_input

SOURCE="006000000000000AAA"
QUOTE="a0P000000000000AAA"
NEW="006000000000000AAB"

def request(mode="CHECK_PRICE",**changes):
    d={"mode":mode,"runMode":"CHECK",
        "sourceOpportunityId":SOURCE,"sourceQuoteId":QUOTE,
        "newOpportunityName":"Korea-Synthetic-New","samples":12,"dataSizeGb":12,
        "productUnitOverrideKrw":"","cloudUnitOverrideKrw":""}
    d.update(changes)
    return d

PRICES={"Product Price Items JSON":'[{"product":"Demo","unit_krw":190000,"qty":12,"net_krw":2280000}]',
        "Product Net KRW":2280000,"Cloud Qty":2,
        "Cloud Net KRW":70000,"Quote Net KRW":2350000,
        "VAT KRW":235000,"Quote Gross KRW":2585000}
READY={"status":"READY","code":"PRICING_VALIDATED","price_fields":PRICES}
PRICE_ONLY={"status":"PRICE_ONLY","code":"MULTI_PRODUCT_QUOTE_FORM_NOT_VERIFIED","price_fields":PRICES}


class WebPairTests(unittest.TestCase):
    def test_check_price_uses_server_authority_only(self):
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=READY) as prepare:
            result=run(request())
        self.assertEqual(result["status"],"PREVIEW_READY")
        self.assertEqual(result["pricing"]["Quote Net KRW"],2350000)
        self.assertFalse(result["salesforce_write"])
        self.assertFalse(result["save_permitted"])
        called=prepare.call_args.args[0]
        self.assertEqual(called["Run Mode"],"CHECK")
        self.assertEqual(called["Source Quote ID"],QUOTE)

    def test_multi_source_is_hold_not_pass(self):
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=PRICE_ONLY):
            result=run(request())
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["code"],"MULTI_PRODUCT_QUOTE_FORM_NOT_VERIFIED")

    def test_check_forms_is_guarded_no_save(self):
        with patch("sfdc_pair_web_preview.process",return_value={
            "status":"PREFLIGHT_PASS","code":"SOURCE_QUOTE_FORM_ONLY",
            "price_fields":PRICES}) as process:
            result=run(request("CHECK_FORMS"))
        self.assertEqual(result["status"],"PREFLIGHT_PASS")
        self.assertFalse(result["save_permitted"])
        self.assertEqual(process.call_args.args[0]["Run Mode"],"CHECK")

    def test_readback_calls_only_existing_pair_check(self):
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=READY) as prepare:
            with patch("sfdc_pair_web_preview.read_live_saved_pair",return_value={
                "status":"PASS","verified":True,"code":"INDEPENDENT_READBACK",
                "new_opportunity_id":NEW,"new_quote_id":"a0P000000000000AAB",
                "net_krw":2350000,"gross_krw":2585000,"cloud_qty":2}) as readback:
                result=run(request("CHECK_READBACK",newOpportunityId=NEW))
        self.assertEqual(result["status"],"PASS")
        self.assertTrue(result["readback"]["verified"])
        self.assertFalse(result["salesforce_write"])
        self.assertEqual(readback.call_args.args[1],NEW)

    def test_readback_multi_block(self):
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=PRICE_ONLY):
            with patch("sfdc_pair_web_preview.read_live_saved_pair") as readback:
                result=run(request("CHECK_READBACK",newOpportunityId=NEW))
        self.assertEqual(result["code"],"MULTI_PRODUCT_NEW_PAIR_READBACK_NOT_SUPPORTED")
        readback.assert_not_called()

    def test_save_modes_rejected_at_edge(self):
        for invalid in [dict(mode="SAVE"),dict(runMode="SAVE"),
                        dict(newOpportunityId=NEW),dict(sourceQuoteId="BAD"),
                        dict(productUnitOverrideKrw=-1),dict(samples=True),
                        dict(dataSizeGb="12")]:
            with self.subTest(invalid=invalid):
                with patch("sfdc_pair_web_preview.prepare_pair") as prepare:
                    result=run(request(**invalid))
                self.assertEqual(result["status"],"BLOCK")
                prepare.assert_not_called()

    def test_readback_must_use_different_parent(self):
        result=run(request("CHECK_READBACK",newOpportunityId=SOURCE))
        self.assertEqual(result["code"],"NEW_OPPORTUNITY_ID_INVALID")

    def test_source_errors_block_without_prices(self):
        with patch("sfdc_pair_web_preview.prepare_pair",return_value={
            "status":"PREFLIGHT_BLOCK","code":"SOURCE_PRODUCT_UNVERIFIED"}):
            result=run(request())
        self.assertEqual(result["status"],"BLOCK")
        self.assertNotIn("pricing",result)

    def test_invalid_rate_float_rejected(self):
        with self.assertRaisesRegex(ValueError,"RATE_INVALID"):
            validate_input(request(productUnitOverrideKrw=190000.5))

if __name__=="__main__":
    unittest.main()
