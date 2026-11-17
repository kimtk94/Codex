import unittest
from sfdc_quote_fee_source import validate

QUOTE = "a0P" + "1" * 12
PRODUCT = "a0N" + "2" * 12
OTHER = "a0N" + "3" * 12

def fixture():
    return {
        "nativeQuoteId": QUOTE, "quoteApiName":"Quotation__c",
        "currency":"KRW","vat":"10,KR-VAT",
        "net": 1500,"custom": 300,"grand": 1980,
        "productIds":[PRODUCT,OTHER],"productCount":2,
        "feeCount":1,"fees":[{
            "feeType":"SP Sample Shipping Fee", "fee":300,
            "feeToCalculate":300,"currency":"KRW",
            "productId":PRODUCT,"productName":"Synthetic Hi-C"
        }]
    }

class FeeNativeSourceTests(unittest.TestCase):
    def test_exact_fee_and_product_match(self):
        a=validate(QUOTE,fixture())
        self.assertEqual(a["status"],"PASS")
        self.assertEqual(a["totalFeeKrw"],300)
        self.assertEqual(a["feeLines"][0]["sourceQuoteProductId"],PRODUCT)
        self.assertFalse(a["salesforce_write"])

    def test_zero_fee_correctly_returns_no_cloned_fee(self):
        x=fixture()
        x.update(custom=0,grand=1650,fees=[],feeCount=0)
        a=validate(QUOTE,x)
        self.assertEqual(a["totalFeeKrw"],0)
        self.assertEqual(a["feeLines"],[])

    def test_other_quote_product_id_must_not_be_accepted(self):
        x=fixture()
        x["fees"][0]["productId"]="a0N"+"4"*12
        with self.assertRaisesRegex(ValueError,"LINK_MISMATCH"):
            validate(QUOTE,x)

    def test_vat_currency_or_total_mismatch_fails_closed(self):
        for update in ({"currency":"USD"},{"vat":"0,HK-VAT"},{"grand":2000}):
            with self.subTest(update=update):
                x=fixture()
                x.update(update)
                with self.assertRaises(ValueError):
                    validate(QUOTE,x)

    def test_invalid_fee_type_or_amount_cannot_be_reused(self):
        for changes in ({"feeType":"Other"},{ "fee":-1},{"feeToCalculate":1}):
            with self.subTest(changes=changes):
                x=fixture()
                x["fees"][0].update(changes)
                with self.assertRaises(ValueError):
                    validate(QUOTE,x)

    def test_missing_fee_rows_block_source(self):
        x=fixture()
        x["fees"]=[]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE"):
            validate(QUOTE,x)

    def test_fee_types_preserve_sample_return_fee(self):
        x=fixture()
        x["fees"][0]["feeType"]="Sample Return Fee"
        self.assertEqual(validate(QUOTE,x)["feeLines"][0]["feeType"],"Sample Return Fee")

if __name__=="__main__":
    unittest.main()
