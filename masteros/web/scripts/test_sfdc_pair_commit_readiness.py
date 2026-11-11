import unittest
import datetime as dt
from unittest.mock import patch
from feishu_sfdc_local_worker import pack_evidence, close_next_month_kst, prepare_pair
from sfdc_pair_web_preview import run

SOURCE="006000000000000AAA"
QUOTE="a0P000000000000AAA"
REQUEST={
  "mode":"CHECK_SAVE_READINESS","runMode":"CHECK",
  "sourceOpportunityId":SOURCE,"sourceQuoteId":QUOTE,
  "newOpportunityName":"Korea-Demo-New-Quote","samples":12,"dataSizeGb":6,
  "productUnitOverrideKrw":"","cloudUnitOverrideKrw":""
}
PRICES={"Sample Unit KRW":120000,"Quote Net KRW":1470000}
QUOTE_DETAIL={
 "pricingStatus":"VERIFIED_PROCESS_LINES","samples":12,"dataSize":6,
 "totalPriceKrw":1470000,
 "processPriceLines":[
  {"packNo":"Pack-A","processName":"QC","sourceQty":12,"unitPriceKrw":20000,"sourceNetKrw":240000,"isCloud":False},
  {"packNo":"Pack-A","processName":"Library","sourceQty":12,"unitPriceKrw":100000,"sourceNetKrw":1200000,"isCloud":False},
  {"packNo":"Cloud","processName":"AliCloud","sourceQty":1,"unitPriceKrw":30000,"sourceNetKrw":30000,"isCloud":True}
 ]}
PREPARED={"status":"READY","price_fields":PRICES,"sourcePackEvidence":
          pack_evidence(QUOTE_DETAIL,12,6,PRICES)}

class PairedCommitReadinessTests(unittest.TestCase):
    def test_calendar_month_clamps_leap_year_and_december(self):
        self.assertEqual(close_next_month_kst(dt.datetime(2026,11,11,16,tzinfo=dt.timezone(dt.timedelta(hours=9)))),"2026-12-11")
        self.assertEqual(close_next_month_kst(dt.datetime(2024,1,31,16,tzinfo=dt.timezone(dt.timedelta(hours=9)))),"2024-02-29")
        self.assertEqual(close_next_month_kst(dt.datetime(2026,12,31,16,tzinfo=dt.timezone(dt.timedelta(hours=9)))),"2027-01-31")
    def test_pack_items_are_authoritatively_projected(self):
        r=pack_evidence(QUOTE_DETAIL,12,6,PRICES)
        self.assertEqual(r["state"],"PASS")
        self.assertEqual([x["quantity"] for x in r["process_lines"]],[12,12,1])
        self.assertEqual(sum(x["projectedNetKrw"] for x in r["process_lines"]),1470000)
        self.assertEqual(r["sample_pack_count"],1)
    def test_pack_missing_or_split_requires_review(self):
        for quote,expected in [
            ({**QUOTE_DETAIL,"processPriceLines":[{**QUOTE_DETAIL["processPriceLines"][0],"packNo":""},*QUOTE_DETAIL["processPriceLines"][1:]]},
              "SOURCE_PACK_OR_PROCESS_LINE_MISSING"),
            ({**QUOTE_DETAIL,"processPriceLines":[QUOTE_DETAIL["processPriceLines"][0],
                {**QUOTE_DETAIL["processPriceLines"][1],"packNo":"Pack-B"},QUOTE_DETAIL["processPriceLines"][2]]},
              "SAME_SAMPLE_MULTIPLE_PACKS_REVIEW_REQUIRED"),
        ]:
            self.assertEqual(pack_evidence(quote,12,6,PRICES)["code"],expected)
    def test_unverified_quote_pack_holds_before_any_automated_form(self):
        p={**PREPARED,"sourcePackEvidence":{"state":"BLOCK","code":"SOURCE_PACK_OR_PROCESS_LINE_MISSING"}}
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=p):
            with patch("sfdc_pair_web_preview.process") as process:
                result=run(REQUEST)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["code"],"SOURCE_PACK_OR_PROCESS_LINE_MISSING")
        self.assertFalse(result["save_permitted"])
        self.assertFalse(result["salesforce_write"])
        process.assert_not_called()
    def test_passed_reference_forms_still_do_not_write_unverified_quote(self):
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=PREPARED):
            with patch("sfdc_pair_web_preview.process",return_value={"status":"PREFLIGHT_PASS"}) as process:
                result=run(REQUEST)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["code"],"QUOTE_PACK_RATE_CLOUD_WRITE_AND_READBACK_NOT_VERIFIED")
        self.assertEqual(result["readiness"]["source_pack"],"PASS")
        self.assertEqual(result["readiness"]["reference_forms"],"PASS")
        self.assertEqual(result["readiness"]["quote_writer"],"UNVERIFIED")
        self.assertFalse(result["save_permitted"])
        process.assert_called_once()
    def test_create_or_save_modes_cannot_bypass_read_only_gate(self):
        for name in ("SAVE","COMMIT","CREATE","CREATE_PAIR","OPPO_ONLY_SAVE"):
            req={**REQUEST,"mode":name}
            with patch("sfdc_pair_web_preview.prepare_pair") as prepare:
                result=run(req)
            self.assertEqual(result["status"],"BLOCK")
            prepare.assert_not_called()
if __name__=="__main__":unittest.main()
