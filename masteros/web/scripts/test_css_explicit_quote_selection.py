import unittest
from unittest.mock import patch
from feishu_sfdc_local_worker import prepare_pair

OPP="006000000000000AAA"
QUOTE="a0P000000000000AAB"
ORIGINAL={"id":OPP,"name":"Original Opportunity",
 "accountId":"001000000000000AAA","contactId":"003000000000000AAA",
 "accountName":"Test Institute","contactName":"Test Researcher"}
OLD={"id":"a0P000000000000AAA","opportunityId":OPP}
BUNDLE={"status":"PASS","selectionStatus":"EXACT_ONE",
        "opportunity":ORIGINAL,"linkedQuotes":[OLD]}
SELECTED={"status":"PASS","id":QUOTE,"opportunityId":OPP,
 "accountId":ORIGINAL["accountId"],"contactId":ORIGINAL["contactId"],
 "productName":"Existing RNA Product","productCategory":"RNA",
 "productCount":1,"processNames":"Preparation,AliCloud",
 "pricingStatus":"VERIFIED_PROCESS_LINES",
 "sourceVatRateVerified10Pct":True,"cloudLinePresent":True,
 "dataSize":12.0,"samples":12,"sourceCloudUnits":2,
 "totalPriceKrw":2350000,"sampleUnitNetKrw":190000,"cloudUnitNetKrw":35000,
 "processPriceLines":[
   {"processType":"Library preparation","processName":"Preparation",
    "packNo":"Pack1","unitPriceKrw":190000,"sourceQty":12,
    "sourceNetKrw":2280000,"isCloud":False},
   {"processType":"Data release","processName":"AliCloud","packNo":"",
    "unitPriceKrw":35000,"sourceQty":2,"sourceNetKrw":70000,"isCloud":True},
 ]}
def request():
 return {"Action":"OPPO_QUOTE_PAIR","Source Oppo ID":OPP,
         "Source Quote ID":QUOTE,"New Opportunity Name":"New-Quote-Request",
         "New Samples":"12","Data Size Gb":"12","Run Mode":"CHECK"}

class ExplicitQuoteSelectionTests(unittest.TestCase):
 def test_selected_quote_is_used_over_other_same_opportunity_quote(self):
  with patch("feishu_sfdc_local_worker.json_run",side_effect=[BUNDLE,SELECTED]) as reader:
   result=prepare_pair(request())
  self.assertEqual(result["status"],"READY")
  self.assertEqual(result["quotation"]["sourceQuoteId"],QUOTE)
  self.assertEqual(result["expectedNet"],2350000)
  self.assertEqual(reader.call_count,2)
  args=reader.call_args_list[1].args[1]
  self.assertEqual(args["recordId"],QUOTE)
  self.assertEqual(args["resource"],"quote")
  self.assertEqual(args["mode"],"detail")
  self.assertTrue(args["forceLive"])
 def test_source_quote_from_other_oppo_blocks(self):
  with patch("feishu_sfdc_local_worker.json_run",
        side_effect=[BUNDLE,{**SELECTED,"opportunityId":"006000000000000AAC"}]):
   result=prepare_pair(request())
  self.assertEqual(result["code"],"SOURCE_PAIR_MISMATCH")
 def test_source_quote_wrong_institution_blocks(self):
  with patch("feishu_sfdc_local_worker.json_run",
        side_effect=[BUNDLE,{**SELECTED,"accountId":"001000000000000AAC"}]):
   result=prepare_pair(request())
  self.assertEqual(result["code"],"SOURCE_QUOTE_CUSTOMER_MISMATCH")
 def test_source_quote_wrong_contact_blocks(self):
  with patch("feishu_sfdc_local_worker.json_run",
        side_effect=[BUNDLE,{**SELECTED,"contactId":"003000000000000AAC"}]):
   result=prepare_pair(request())
  self.assertEqual(result["code"],"SOURCE_QUOTE_CUSTOMER_MISMATCH")
 def test_missing_contact_id_blocks(self):
  with patch("feishu_sfdc_local_worker.json_run",
        side_effect=[BUNDLE,{**SELECTED,"contactId":""}]):
   result=prepare_pair(request())
  self.assertEqual(result["code"],"SOURCE_QUOTE_CUSTOMER_LINK_UNVERIFIED")
 def test_source_unavailable_blocks(self):
  with patch("feishu_sfdc_local_worker.json_run",
        side_effect=[BUNDLE,{"status":"BLOCK","code":"SFDC_UI_UNAVAILABLE"}]):
   result=prepare_pair(request())
  self.assertEqual(result["code"],"SOURCE_SELECTED_QUOTE_READ_UNAVAILABLE")
 def test_explicit_quote_does_not_bypass_user_edited_prices(self):
  with patch("feishu_sfdc_local_worker.json_run",side_effect=[BUNDLE,SELECTED]):
   result=prepare_pair({**request(),"Requested Product Unit KRW":"200000"})
  self.assertEqual(result["status"],"READY")
  self.assertEqual(result["price_fields"]["Price Status"],"MANUAL_OVERRIDE_REVIEW_REQUIRED")
if __name__=="__main__":unittest.main()
