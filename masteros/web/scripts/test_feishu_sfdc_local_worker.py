import unittest
from types import SimpleNamespace
from unittest.mock import patch
from feishu_sfdc_local_worker import validate,prepare_pair,process,HEAD,json_run
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
 "samples":42,"sourceCloudUnits":6,"totalPriceKrw":8190000,
 "sampleUnitNetKrw":190000,"cloudUnitNetKrw":35000,"productName":"Existing RNA Product",
 "productCategory":"RNA","processNames":"Preparation,AliCloud",
 "processPriceLines":[
    {"processName":"Preparation","unitPriceKrw":190000,"sourceQty":42,
     "sourceNetKrw":7980000,"isCloud":False},
    {"processName":"AliCloud","unitPriceKrw":35000,"sourceQty":6,
     "sourceNetKrw":210000,"isCloud":True}]}]}
def base(**kw):
    x={"Action":"OPPO_QUOTE_PAIR","Source Oppo ID":"006000000000000AAA",
       "Source Quote ID":"a0P000000000000AAA","New Opportunity Name":"New-12",
       "New Samples":"12","Data Size Gb":"12","Run Mode":"CHECK"}
    x.update(kw)
    return x
class T(unittest.TestCase):
 def test_windows_subprocess_handles_korean_utf8(self):
    with patch("feishu_sfdc_local_worker.subprocess.run",
      return_value=SimpleNamespace(stdout='{"status":"PREFLIGHT_PASS"}')) as run:
      result=json_run("sfdc_action_executor.py",{"progressDescription":"신규 샘플 준비"})
    self.assertEqual(result["status"],"PREFLIGHT_PASS")
    self.assertEqual(run.call_args.kwargs["encoding"],"utf-8")
    self.assertEqual(run.call_args.kwargs["env"]["PYTHONIOENCODING"],"utf-8")
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
    self.assertEqual(p["price_fields"]["Product Unit KRW"],190000)
    self.assertEqual(p["price_fields"]["Product Qty"],12)
    self.assertEqual(p["price_fields"]["Product Net KRW"],2280000)
    self.assertEqual(p["price_fields"]["Cloud Net KRW"],70000)
    self.assertEqual(p["price_fields"]["Quote Net KRW"],2350000)
    self.assertIn("sourcePackEvidence",p)
    self.assertNotIn("source progress",p["opportunity"]["progressDescription"].lower())
 def test_single_product_ready_propagates_verified_pack_and_price_lines(self):
    from copy import deepcopy
    source=deepcopy(SOURCE)
    for row in source["linkedQuotes"][0]["processPriceLines"]:
      row["packNo"]="" if row["isCloud"] else "Package1"
      row["processType"]="Data release" if row["isCloud"] else "Library preparation"
    with patch("feishu_sfdc_local_worker.json_run",return_value=source):
      prepared=prepare_pair(base())
    self.assertEqual(prepared["status"],"READY")
    self.assertEqual(prepared["sourcePackEvidence"]["state"],"PASS")
    self.assertEqual(prepared["sourcePackEvidence"]["sample_pack_count"],1)
    self.assertEqual(len(prepared["sourcePackEvidence"]["process_lines"]),2)
    self.assertEqual(sum(item["projectedNetKrw"] for item in prepared["sourcePackEvidence"]["process_lines"]),2350000)

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
 def test_user_changes_product_rate(self):
    with patch("feishu_sfdc_local_worker.json_run",return_value=SOURCE):
      p=prepare_pair(base(**{"Requested Product Unit KRW":"200000"}))
    self.assertEqual(p["status"],"READY")
    self.assertEqual(p["price_fields"]["Price Status"],"MANUAL_OVERRIDE_REVIEW_REQUIRED")
    self.assertEqual(p["expectedNet"],2470000)
 def test_user_changes_cloud_rate(self):
    with patch("feishu_sfdc_local_worker.json_run",return_value=SOURCE):
      p=prepare_pair(base(**{"Requested Cloud Unit KRW":"40000"}))
    self.assertEqual(p["expectedNet"],2360000)
    self.assertEqual(p["price_fields"]["Cloud Unit KRW"],40000)
 def test_unverified_source_total_blocks(self):
    src={**SOURCE,"linkedQuotes":[{**SOURCE["linkedQuotes"][0],"totalPriceKrw":100}]}
    with patch("feishu_sfdc_local_worker.json_run",return_value=src):
      p=prepare_pair(base())
    self.assertEqual(p["code"],"SOURCE_QUOTE_RECONCILIATION_FAILED")
 def test_no_new_request(self):
    self.assertFalse(validate(row(Approval="")))
 def test_two_forms_preflight_reference_only_without_save(self):
    responses=[SOURCE,{"status":"PREFLIGHT_PASS","save_clicked":False},
        {"status":"PREFLIGHT_PASS","save_clicked":False,"product_added":False}]
    with patch("feishu_sfdc_local_worker.json_run",side_effect=responses) as runner:
      result=process(base())
    self.assertEqual(result["status"],"PREFLIGHT_PASS")
    self.assertIn("REFERENCE_QUOTE_FORM_ONLY_NO_SAVE",result["code"])
    self.assertEqual(result["price_fields"]["Quote Net KRW"],2350000)
    self.assertEqual(runner.call_count,3)
    self.assertEqual(runner.call_args_list[1].args[1]["action"],"opportunity_create")
    self.assertEqual(runner.call_args_list[2].args[1]["action"],"quote_create")
    self.assertEqual(runner.call_args_list[2].args[1]["mode"],"check")
    self.assertEqual(runner.call_args_list[2].args[1]["opportunityId"],base()["Source Oppo ID"])
 def test_quote_reference_form_failure_blocks(self):
    responses=[SOURCE,{"status":"PREFLIGHT_PASS","save_clicked":False},
        {"status":"BLOCK","code":"QUOTE_CATALOG_AMBIGUOUS","save_clicked":False}]
    with patch("feishu_sfdc_local_worker.json_run",side_effect=responses):
      result=process(base())
    self.assertEqual(result["status"],"PREFLIGHT_BLOCK")
    self.assertEqual(result["code"],"QUOTE_CATALOG_AMBIGUOUS")
 def test_even_a_rogue_save_clicked_flag_blocks_preflight(self):
    responses=[SOURCE,{"status":"PREFLIGHT_PASS","save_clicked":False},
        {"status":"PREFLIGHT_PASS","save_clicked":True,"product_added":False}]
    with patch("feishu_sfdc_local_worker.json_run",side_effect=responses):
      result=process(base())
    self.assertEqual(result["status"],"PREFLIGHT_BLOCK")
    self.assertEqual(result["code"],"QUOTE_REFERENCE_NO_SAVE_PREFLIGHT_FAILED")
 def test_pair_save_does_not_even_call_ui(self):
    with patch("feishu_sfdc_local_worker.json_run",return_value=SOURCE) as runner:
      result=process(base(**{"Run Mode":"SAVE"}))
    self.assertEqual(result["status"],"BLOCK")
    self.assertEqual(runner.call_count,1)
if __name__=="__main__":unittest.main()
