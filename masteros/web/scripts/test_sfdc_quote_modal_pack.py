"""SFDC Quote Add/Edit matrix regression: source fields, price, Pack and Cloud, no save."""
import copy
import unittest
from unittest.mock import patch
from sfdc_record_catalog import parse_modal_process_price_rows
from feishu_sfdc_local_worker import pack_evidence

def row(num,pack,category,process,samples,size,rate,standard):
    def c(text="",value=None):
        return {"text":str(text),"value":value}
    return [c(num),c(),c(pack),c(category),c(process),
      c(value=samples),c(value=size),c("G raw data"),c(value=rate),
      c(standard),c(),c(),c()]
def fixture():
    return {"headers":["","","Pack No.","Process Name","Process Type",
        "Sample Number","Data Size","Data Unit","Unit Price","Standard Price",
        "Note","",""],
        "rows":[
          row(1,"Package1","Library preparation","mRNA library preparation (poly A enrichment)",
            "12.00","5.00","160,000.00","135000"),
          row(2,"Package1","Sequencing by data amount","NovaSeq X Plus (PE150)",
            "12.00","5.00","0.00","48750"),
          row(3,"Package1","Analysis by sample","Data quality control",
            "12.00","5.00","0.00","0"),
          row(4,"","Data release","AliCloud",
            "1.00","1.00","35,000.00","30000"),
        ],"total":"1955000"}

class ModalPackTests(unittest.TestCase):
    def verify(self,value=None):
        return parse_modal_process_price_rows(value or fixture(),12,5,1955000)
    def test_source_uses_actual_quote_unit_price_not_standard_price(self):
        p=self.verify()
        self.assertEqual(p["pricingStatus"],"VERIFIED_PROCESS_LINES")
        self.assertEqual(p["sampleUnitNetKrw"],160000)
        self.assertEqual(p["cloudUnitNetKrw"],35000)
        self.assertEqual(p["sourceCloudUnits"],1)
        self.assertEqual(p["sourceProcessNetKrw"],1955000)
        self.assertEqual([r["standardPriceKrw"] for r in p["processPriceLines"]],
            [135000,48750,0,30000])
        self.assertEqual(p["pricingMethod"],"READ_ONLY_SFDC_ADD_EDIT_UNIT_PRICE_MATRIX")
    def test_sample_pack_and_release_not_packed(self):
        p=self.verify()
        self.assertEqual(p["sourceSamplePackNo"],"Package1")
        self.assertEqual(p["processPriceLines"][-1]["packNo"],"")
        p["samples"]=12;p["dataSize"]=5;p["totalPriceKrw"]=1955000
        expected={"Quote Net KRW":1955000,"Sample Unit KRW":160000}
        e=pack_evidence(p,12,5,expected)
        self.assertEqual(e["state"],"PASS")
        self.assertEqual(e["sample_pack_count"],1)
        self.assertEqual(sum(r["projectedNetKrw"] for r in e["process_lines"]),1955000)
    def test_different_sample_pack_blocks(self):
        f=fixture();f["rows"][1][2]["text"]="Package2"
        with self.assertRaisesRegex(ValueError,"SOURCE_SAME_SAMPLE_PACK_CONFLICT"):
            self.verify(f)
    def test_incorrect_total_blocks(self):
        f=fixture();f["total"]="1954000"
        with self.assertRaisesRegex(ValueError,"SOURCE_MODAL_QUOTE_NET_MISMATCH"):
            self.verify(f)
    def test_missing_cloud_blocks(self):
        f=fixture();f["rows"]=f["rows"][:-1]
        with self.assertRaisesRegex(ValueError,"SOURCE_CLOUD_OR_SERVICE_NOT_UNIQUE"):
            self.verify(f)
    def test_wrong_gb_or_sample_quantity_blocks(self):
        f=fixture();f["rows"][0][5]["value"]="11.00"
        with self.assertRaisesRegex(ValueError,"SOURCE_PROCESS_QUANTITY_MISMATCH"):
            self.verify(f)
        f=fixture();f["rows"][1][6]["value"]="6.00"
        with self.assertRaisesRegex(ValueError,"SOURCE_PROCESS_GB_MISMATCH"):
            self.verify(f)
    def test_reference_standard_price_not_substituted(self):
        f=fixture();f["rows"][0][8]["value"]="135,000.00"
        with self.assertRaisesRegex(ValueError,"SOURCE_MODAL_QUOTE_NET_MISMATCH"):
            self.verify(f)
    def test_changed_modal_schema_blocks(self):
        f=fixture();f["headers"][8]="Sales Price"
        with self.assertRaisesRegex(ValueError,"SOURCE_MODAL_HEADERS_CHANGED"):
            self.verify(f)
    def test_non_whole_krw_blocks(self):
        f=fixture();f["rows"][0][8]["value"]="160,000.25"
        with self.assertRaisesRegex(ValueError,"PROCESS_MODAL_NUMBER_INVALID"):
            self.verify(f)

if __name__=="__main__":
    unittest.main()
