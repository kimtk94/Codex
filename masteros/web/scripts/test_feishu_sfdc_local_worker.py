import unittest
from unittest.mock import patch
from feishu_sfdc_local_worker import validate,prepare_pair,process,HEAD
def row(**kw):
    d={k:"" for k in HEAD};d.update({"record_id":"rec_TEST","Action":"OPPO_QUOTE_PAIR",
    "Status":"NEW","Run Mode":"CHECK","Approval":"PREFLIGHT"})
    d.update(kw)
    return [d[k] for k in HEAD]
SOURCE={"status":"PASS","selectionStatus":"EXACT_ONE",
 "opportunity":{"id":"006000000000000AAA","name":"Original-42","accountId":"001000000000000AAA",
                "contactId":"003000000000000AAA","accountName":"Example Univ",
                "contactName":"Example Customer"},
 "linkedQuotes":[{"id":"a0P000000000000AAA","opportunityId":"006000000000000AAA",
 "pricingStatus":"VERIFIED_PROCESS_LINES","sourceVatRateVerified10Pct":True,
 "cloudLinePresent":True,"productCount":1,"dataSize":12.0,
 "sampleUnitNetKrw":190000,"cloudUnitNetKrw":35000,"productName":"Existing RNA Product",
 "productCategory":"RNA","processNames":"Preparation,AliCloud"}]}
def base(**kw):
    x={"Action":"OPPO_QUOTE_PAIR","Source Oppo ID":"006000000000000AAA",
       "Source Quote ID":"a0P000000000000AAA","New Opportunity Name":"New-12",
       "New Samples":"12","Data Size Gb":"12","Run Mode":"CHECK"}
    x.update(kw)
    return x
class T(unittest.TestCase):
 def test_new_request(self):
    self.assertTrue(validate(row()))
    self.assertFalse(validate(row(**{"Run Mode":"SAVE"})))
 def test_approval_save(self):
    self.assertTrue(validate(row(**{"Run Mode":"SAVE","Approval":"APPROVED",
      "Duplicate Checked":"YES","Price Checked":"YES"})))
 def test_no_retry(self):
    self.assertFalse(validate(row(Status="RUNNING")))
    self.assertFalse(validate(row(Status="PASS")))
 def test_price_144_gb(self):
    with patch("feishu_sfdc_local_worker.json_run",return_value=SOURCE):
      p=prepare_pair(base())
    self.assertEqual(p["status"],"READY")
    self.assertEqual(p["expectedCloudUnits"],2)
    self.assertEqual(p["expectedNet"],2350000)
    self.assertEqual(p["expectedGross"],2585000)
    self.assertNotIn("source progress",p["opportunity"]["progressDescription"].lower())
 def test_data_size_change_blocked(self):
    with patch("feishu_sfdc_local_worker.json_run",return_value=SOURCE):
      p=prepare_pair(base(**{"Data Size Gb":"15"}))
    self.assertEqual(p["code"],"DATA_SIZE_RATE_UNVERIFIED")
 def test_wrong_source_quote_blocked(self):
    with patch("feishu_sfdc_local_worker.json_run",return_value=SOURCE):
      p=prepare_pair(base(**{"Source Quote ID":"a0P000000000000AAB"}))
    self.assertEqual(p["code"],"SOURCE_PAIR_MISMATCH")
 def test_pair_save_never_partially_creates_opp(self):
    with patch("feishu_sfdc_local_worker.json_run",return_value=SOURCE):
      p=process(base(**{"Run Mode":"SAVE"}))
    self.assertEqual(p["status"],"BLOCK")
    self.assertEqual(p["code"],"CLOUD_PROCESS_SAVE_READBACK_NOT_VERIFIED")
 def test_no_new_request(self):
    self.assertFalse(validate(row(Approval="")))
if __name__=="__main__":unittest.main()
