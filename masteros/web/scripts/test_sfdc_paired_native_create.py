import unittest
from unittest.mock import patch
from sfdc_native_process_writer import validated_price_plan,verify_native_matrix
from sfdc_paired_native_create import request_from_queue,build_live_plan,plan_digest

def row(typ,name,qty,price,cloud=False,pack="Package1"):
 return {"processType":typ,"processName":name,"quantity":qty,
         "unitPriceKrw":price,"isCloud":cloud,"packNo":"" if cloud else pack}

def cell(text="",value=None):return {"text":text,"value":value}
def matrix(lines,gb=5):
 data=[]
 for idx,line in enumerate(lines):
  data.append([cell(str(idx+1)),cell(),cell("" if line["isCloud"] else "Package99"),
   cell(line["processType"]),cell(line["processName"]),
   cell(value=f'{line["quantity"]}.00'),cell(value="1.00" if line["isCloud"] else str(gb)),
   cell("G raw data"),cell(value=f'{line["unitPriceKrw"]:,.2f}'),
   cell("987654"),cell(),cell(),cell()])
 return {"headers":["","","Pack No.","Process Name","Process Type","Sample Number",
          "Data Size","Data Unit","Unit Price","Standard Price","Note","",""],
         "rows":data,
         "total":str(sum(x["quantity"]*x["unitPriceKrw"] for x in lines))}

def canonical():
 return {"reference":{"opportunityId":"006000000000001AAA",
                        "sourceQuoteId":"a0P000000000001AAA","qid":"QID-2026-11-18-123456"},
    "proposed":{"name":"Korea-Test-Single-Quote-6Gb","closeDate":"2026-12-18",
      "description":"1118 Quote Draft mRNA-Seq 5Gb 4 samples * 160,000KRW",
      "accountMode":"KEEP","quoteFeeMode":"EXCLUDE","quoteFeeLines":[],
      "account":{"id":"001000000000001AAA","name":"University"},
      "contact":{"id":"003000000000001AAA","name":"Professor"},
      "products":[{"sourceQuoteProductId":"QD-123","id":"QD-123",
        "serviceLabel":"mRNA-Seq","samples":"4","productionGb":"5",
        "sampleUnitKrw":"160000","cloudUnitKrw":"35000",
        "priceEvidenceStatus":"LIVE_SFDC_KRW_VERIFIED",
        "processNames":["mRNA library preparation","NovaSeq X Plus (PE150)","Data quality control","AliCloud"],
        "processIds":["Process-2020-01-01-00001","Process-2020-01-01-00002",
                      "Process-2020-01-01-00003","Process-2020-01-01-00004"],
        "fixedProcessLines":[],"amplicon":{"enabled":False}}]},
    "review":{"preflightStatus":"PREVIEW_READY",
      "verifiedNativeRateForUnchangedAmount":True,"priceChangeRequiresApproval":False}}

class PureNativeSaveTests(unittest.TestCase):
 def test_native_plan_and_matrix_exact_customer_rates(self):
  lines=[row("Library preparation","mRNA library preparation",4,160000),
         row("Sequencing by data amount","NovaSeq X Plus (PE150)",4,0),
         row("Analysis by sample","Data quality control",4,0),
         row("Data release","AliCloud",1,35000,True)]
  plan=validated_price_plan(lines,4,5,675000)
  self.assertEqual(plan["expectedNet"],675000)
  self.assertEqual(plan["cloudUnits"],1)
  x=verify_native_matrix(plan,matrix(plan["lines"]))
  self.assertEqual(x["status"],"PASS")
  self.assertEqual(x["samplePackCount"],1)
 def test_alicloud_rounds_100gb_blocks_exactly(self):
  lines=[row("Library preparation","Lib",20,160000),
         row("Data release","AliCloud",2,35000,True)]
  plan=validated_price_plan(lines,20,5.01,3270000)
  self.assertEqual(plan["cloudUnits"],2)
  self.assertEqual(verify_native_matrix(plan,matrix(plan["lines"],gb=5.01))["cloudUnits"],2)
 def test_reject_price_qty_pack_cloud_and_total_mismatch(self):
  lines=[row("Library preparation","Lib",4,160000),
         row("Data release","AliCloud",1,35000,True)]
  plan=validated_price_plan(lines,4,5,675000)
  for alter in ("price","qty","pack","total","duplicate"):
   bad=matrix(plan["lines"])
   if alter=="price":bad["rows"][0][8]["value"]="200,000.00"
   if alter=="qty":bad["rows"][1][5]["value"]="2.00"
   if alter=="pack":bad["rows"][0][2]["text"]=""
   if alter=="total":bad["total"]="675001"
   if alter=="duplicate":bad["rows"][1][3]["text"]="Library preparation";bad["rows"][1][4]["text"]="Lib"
   with self.subTest(alter=alter),self.assertRaises(ValueError):
    verify_native_matrix(plan,bad)
  wrong=[dict(x) for x in lines]
  wrong[1]["quantity"]=3
  with self.assertRaisesRegex(ValueError,"QTY"):
   validated_price_plan(wrong,4,5,675000)
 def test_exact_plan_digest_detects_price_redistribution_same_total(self):
  # Previous consent signed only Quote net. Two process rates can change
  # while their combined net remains identical; do not allow that drift.
  import copy
  p=validated_price_plan([
   row("Library preparation","Lib",4,150000),
   row("Sequencing by data amount","Seq",4,10000),
   row("Data release","AliCloud",1,35000,True)],4,5,675000)
  one=plan_digest({"pricePlan":p})
  q=copy.deepcopy(p)
  q["lines"][0]["unitPriceKrw"]=140000
  q["lines"][1]["unitPriceKrw"]=20000
  self.assertEqual(sum(x["quantity"]*x["unitPriceKrw"] for x in p["lines"]),
                   sum(x["quantity"]*x["unitPriceKrw"] for x in q["lines"]))
  self.assertNotEqual(one,plan_digest({"pricePlan":q}))
  q=copy.deepcopy(p)
  q["lines"][0]["packNo"]="PackageB"
  self.assertNotEqual(one,plan_digest({"pricePlan":q}))
 def test_validate_queue_source_mode_and_price(self):
  raw=canonical()
  parsed=request_from_queue(raw)
  self.assertEqual(parsed["expectedNet"],675000)
  self.assertEqual(parsed["samples"],4)
  raw["proposed"]["products"][0]["fixedProcessLines"]=[{"processName":"Data release"}]
  with self.assertRaisesRegex(ValueError,"NATIVE_REVIEW"):
   request_from_queue(raw)
 def test_exact_original_name_is_allowed_in_private_approved_clone(self):
  # Source Opportunity and new Opportunity can share a display name:
  # Salesforce ID, immutable queued digest and claim are the identity keys.
  p=canonical()
  p["proposed"]["name"]="Korea-Test-Single-Quote-6Gb"
  x=request_from_queue(p)
  self.assertEqual(x["name"],p["proposed"]["name"])
  self.assertEqual(x["sourceOpportunityId"],"006000000000001AAA")
 def test_prepare_pair_retains_exact_source_opportunity_name(self):
  from feishu_sfdc_local_worker import prepare_pair
  src_opp={"id":"006000000000001AAA","name":"Korea-Test-Single-Quote-6Gb",
    "accountId":"001000000000001AAA","contactId":"003000000000001AAA",
    "accountName":"University","contactName":"Professor"}
  source={"id":"a0P000000000001AAA","opportunityId":"006000000000001AAA",
    "pricingStatus":"VERIFIED_PROCESS_LINES",
    "sourceVatRateVerified10Pct":True,"cloudLinePresent":True,
    "productCount":1,"dataSize":5,"productCategory":"RNA",
    "productName":"RNA Product","processNames":"Lib,Seq,AliCloud"}
  bundle={"status":"PASS","opportunity":src_opp,"linkedQuotes":[source]}
  prices={"Cloud Qty":1,"Quote Net KRW":675000,"Quote Gross KRW":742500,
    "Sample Unit KRW":160000,"Cloud Unit KRW":35000}
  request={"Source Oppo ID":src_opp["id"],"Source Quote ID":source["id"],
    "New Samples":"4","Data Size Gb":"5",
    "New Opportunity Name":src_opp["name"]}
  with patch("feishu_sfdc_local_worker.json_run",return_value=bundle), \
       patch("feishu_sfdc_local_worker.evaluate_price",return_value=prices), \
       patch("feishu_sfdc_local_worker.pack_evidence",
             return_value={"state":"PASS","process_lines":[]}):
   actual=prepare_pair(request)
  self.assertEqual(actual["status"],"READY",actual)
  self.assertEqual(actual["opportunity"]["opportunityName"],src_opp["name"])
 def test_block_drifted_price_or_customer_before_save(self):
  fake={"status":"READY","expectedNet":676000,
        "price_fields":{"Sample Unit KRW":160000,"Cloud Unit KRW":35000},
        "sourcePackEvidence":{"state":"PASS","process_lines":[]},
        "opportunity":{"accountId":"001000000000001AAA","contactId":"003000000000001AAA",
          "accountName":"University","contactName":"Professor"},
        "quotation":{"processNames":"mRNA library preparation,NovaSeq X Plus (PE150),Data quality control,AliCloud"}}
  with patch("feishu_sfdc_local_worker.prepare_pair",return_value=fake):
   result,data=build_live_plan(canonical())
  self.assertEqual(result["status"],"BLOCK")
  self.assertEqual(result["code"],"NATIVE_PRICE_MISMATCH_REAPPROVAL_REQUIRED")

if __name__=="__main__":
 unittest.main()
