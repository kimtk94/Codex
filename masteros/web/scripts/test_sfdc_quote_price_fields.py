import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]/"automation"/"feishu"))
from sfdc_quote_price_fields import evaluate,PriceError,PRICE_INPUT_FIELDS,PRICE_RESULT_FIELDS

def quote():
    return {
        "pricingStatus":"VERIFIED_PROCESS_LINES",
        "sourceVatRateVerified10Pct":True,
        "productCount":1,"productName":"Example mRNA Sequencing",
        "cloudLinePresent":True,
        "samples":42,"dataSize":12,"sourceCloudUnits":6,
        "sampleUnitNetKrw":190000,"cloudUnitNetKrw":35000,
        "totalPriceKrw":8190000,
        "processPriceLines":[
            {"processName":"RNA library", "sourceQty":42,"unitPriceKrw":70000,
             "sourceNetKrw":2940000,"isCloud":False},
            {"processName":"PE150 sequencing","sourceQty":42,"unitPriceKrw":120000,
             "sourceNetKrw":5040000,"isCloud":False},
            {"processName":"AliCloud","sourceQty":6,"unitPriceKrw":35000,
             "sourceNetKrw":210000,"isCloud":True}
        ]}

class QuotePriceBreakdownTests(unittest.TestCase):
    def test_single_product_two_charge_types(self):
        p=evaluate(quote(),12,12)
        self.assertEqual((p["Product Unit KRW"],p["Sample Unit KRW"]),(190000,190000))
        self.assertEqual((p["Product Qty"],p["Product Net KRW"]),(12,2280000))
        self.assertEqual((p["Cloud Qty"],p["Cloud Net KRW"]),(2,70000))
        self.assertEqual((p["Quote Net KRW"],p["VAT KRW"],p["Quote Gross KRW"]),
                         (2350000,235000,2585000))
        self.assertIn("RNA library",p["Product Price Detail"])
        self.assertEqual(p["Price Status"],"SOURCE_VERIFIED_PROJECTION")
    def test_source_42_samples(self):
        p=evaluate(quote(),42,12)
        self.assertEqual((p["Cloud Qty"],p["Quote Net KRW"]),(6,8190000))
    def test_exact_100gb_boundary(self):
        p=evaluate(quote(),1,12)
        self.assertEqual(p["Cloud Qty"],1)
    def test_manual_product_override_requires_review(self):
        p=evaluate(quote(),12,12,"200000","")
        self.assertEqual((p["Product Net KRW"],p["Quote Net KRW"]),(2400000,2470000))
        self.assertEqual(p["Price Status"],"MANUAL_OVERRIDE_REVIEW_REQUIRED")
    def test_manual_cloud_override_requires_review(self):
        p=evaluate(quote(),12,12,"","40000")
        self.assertEqual(p["Cloud Net KRW"],80000)
        self.assertEqual(p["Quote Net KRW"],2360000)
        self.assertEqual(p["Price Status"],"MANUAL_OVERRIDE_REVIEW_REQUIRED")
    def test_source_line_mismatch_blocks(self):
        q=quote();q["processPriceLines"][0]["sourceNetKrw"]=1
        with self.assertRaisesRegex(PriceError,"PROCESS_LINE_ARITHMETIC_MISMATCH"):
            evaluate(q,12,12)
    def test_cloud_quantity_mismatch_blocks(self):
        q=quote();q["sourceCloudUnits"]=5
        with self.assertRaisesRegex(PriceError,"SOURCE_QUOTE_RECONCILIATION_FAILED"):
            evaluate(q,12,12)
    def test_multiple_cloud_blocks(self):
        q=quote();q["processPriceLines"].append(q["processPriceLines"][-1].copy())
        with self.assertRaisesRegex(PriceError,"MULTI_CLOUD"):
            evaluate(q,12,12)
    def test_price_change_without_data_rate_blocks(self):
        with self.assertRaisesRegex(PriceError,"DATA_SIZE_RATE_UNVERIFIED"):
            evaluate(quote(),12,15)
    def test_invalid_override_blocks(self):
        with self.assertRaisesRegex(PriceError,"PRICE_RATE_INVALID"):
            evaluate(quote(),12,12,"text")
    def test_queue_schema_consistency(self):
        from sfdc_command_queue import PRICE_INPUT_FIELDS as inputs,PRICE_RESULT_FIELDS as result
        self.assertEqual(inputs,PRICE_INPUT_FIELDS)
        self.assertEqual(result,PRICE_RESULT_FIELDS)

if __name__=="__main__":unittest.main()
