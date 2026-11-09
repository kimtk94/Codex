import os
import unittest
from unittest.mock import patch,Mock
from sfdc_price_smoke import KEY,NAME,SmokeError,seed,verify,cleanup
from sfdc_command_queue import HEAD

class FeishuPriceE2ETests(unittest.TestCase):
    def test_seed_requires_sealed_sources(self):
        with patch("sfdc_price_smoke.locate",return_value=[]),patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(SmokeError,"SOURCE_SECRETS_UNAVAILABLE"):
                seed("test","tblTEST")
    def test_seed_always_read_only(self):
        f={"record_id":"recTEST","fields":{"Request ID":KEY,"Action":"OPPO_QUOTE_PAIR",
          "Source Oppo ID":"006000000000000AAA","Source Quote ID":"a0P000000000000AAA",
          "New Opportunity Name":NAME,"New Samples":"12","Data Size Gb":"12",
          "Approval":"PREFLIGHT","Run Mode":"CHECK","Status":"NEW"}}
        env={"CSS_SFDC_SMOKE_OPPO_ID":f["fields"]["Source Oppo ID"],
             "CSS_SFDC_SMOKE_QUOTE_ID":f["fields"]["Source Quote ID"]}
        with patch.dict(os.environ,env),patch("sfdc_price_smoke.locate",side_effect=[[],[f]]):
            with patch("sfdc_price_smoke.call",return_value={"record":{"record_id":"recTEST"}}) as api:
                out=seed("token","tbl")
        self.assertTrue(out["read_only"])
        self.assertEqual(api.call_args.args[0],"POST")
        self.assertEqual(api.call_args.args[3]["fields"]["Run Mode"],"CHECK")
    def test_cleanup_blocks_other_user_records(self):
        f={"record_id":"recTEST","fields":{"Request ID":KEY,
          "Run Mode":"CHECK","Approval":"PREFLIGHT","Status":"PREFLIGHT_PASS"}}
        other=["recOTHER"]+[""]*(len(HEAD)-1)
        with patch("sfdc_price_smoke.locate",return_value=[f]):
            with patch("sfdc_price_smoke.google",return_value=object()),patch(
                "sfdc_price_smoke.mirror",return_value={"recTEST":["recTEST",KEY],
                                                        "recOTHER":other}):
                with patch("sfdc_price_smoke.call") as c:
                    with self.assertRaisesRegex(SmokeError,"OTHER_ROWS_PRESENT"):
                        cleanup("token","tbl")
                    c.assert_not_called()
    def test_verify_reconciles_product_and_cloud_and_mirror(self):
        numbers={"Sample Unit KRW":190000,"Product Unit KRW":190000,
          "Product Qty":12,"Product Net KRW":2280000,"Cloud Unit KRW":35000,
          "Cloud Qty":2,"Cloud Net KRW":70000,"Quote Net KRW":2350000,
          "VAT KRW":235000,"Quote Gross KRW":2585000}
        f={"Status":"PREFLIGHT_PASS","Request ID":KEY,
          "Price Status":"SOURCE_VERIFIED_PROJECTION",**numbers}
        values=[""]*len(HEAD);values[0]="recTEST"
        for k,v in f.items():values[HEAD.index(k)]=str(v)
        with patch("sfdc_price_smoke.locate",return_value=[{"fields":f}]):
            with patch("sfdc_price_smoke.google",return_value=object()),patch(
                "sfdc_price_smoke.mirror",return_value={"recTEST":values}):
                r=verify("token","tbl")
        self.assertEqual(r["status"],"PASS")
        self.assertEqual(r["net_krw"],2350000)
        self.assertEqual(r["cloud_qty"],2)
        self.assertEqual(r["crm_writes"],0)

if __name__=="__main__":unittest.main()
