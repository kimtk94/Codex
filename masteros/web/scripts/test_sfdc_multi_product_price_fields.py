"""Synthetic multi-product Source Quote contract; no Salesforce or customer data."""
import copy
import json
import unittest
from unittest.mock import patch

from sfdc_quote_price_fields import evaluate_multi, PriceError, PRICE_RESULT_FIELDS
from feishu_sfdc_local_worker import prepare_pair, process


def example_quote():
    return {
        "id":"a0P000000000000AAA","opportunityId":"006000000000000AAA",
        "pricingStatus":"VERIFIED_MULTI_PRODUCT_LINES",
        "sourceVatRateVerified10Pct":True,
        "productCount":2,"samples":12,"dataSize":12.0,
        "totalPriceKrw":3670000,"grandTotalKrw":4037000,
        "sourceCloudUnits":2,"cloudUnitNetKrw":35000,
        "sourceProductLines":[
            {
                "productKey":"lineA","productName":"Service A","sourceQty":12,
                "dataGbPerSample":5.0,"sourceNetKrw":1320000,
                "processPriceLines":[
                    {"processName":"Library A","sourceQty":12,"unitPriceKrw":40000,
                     "sourceNetKrw":480000,"isCloud":False},
                    {"processName":"Sequencing A","sourceQty":12,"unitPriceKrw":70000,
                     "sourceNetKrw":840000,"isCloud":False}],
            },
            {
                "productKey":"lineB","productName":"Service B","sourceQty":12,
                "dataGbPerSample":7.0,"sourceNetKrw":2280000,
                "processPriceLines":[
                    {"processName":"Sequencing B","sourceQty":12,"unitPriceKrw":190000,
                     "sourceNetKrw":2280000,"isCloud":False}],
            },
        ],
        "cloudProcessLine":{"processName":"AliCloud","sourceQty":2,
            "unitPriceKrw":35000,"sourceNetKrw":70000,"isCloud":True},
    }


def example_request(**changes):
    request={
        "Action":"OPPO_QUOTE_PAIR","Run Mode":"CHECK",
        "Source Oppo ID":"006000000000000AAA",
        "Source Quote ID":"a0P000000000000AAA",
        "New Opportunity Name":"Two-Product-20",
        "New Samples":"20","Data Size Gb":"12",
        "Requested Product Unit KRW":"","Requested Cloud Unit KRW":"",
    }
    request.update(changes)
    return request


def example_bundle():
    return {
        "status":"PASS","selectionStatus":"EXACT_ONE",
        "opportunity":{
            "id":"006000000000000AAA","name":"Reference Opportunity",
            "accountId":"001000000000000AAA","contactId":"003000000000000AAA",
            "accountName":"Example Org","contactName":"Example Contact",
        },
        "linkedQuotes":[example_quote()],
    }


class MultiProductTests(unittest.TestCase):
    def test_separate_units_and_one_shared_cloud(self):
        result=evaluate_multi(example_quote(),20,12.0)
        items=json.loads(result["Product Price Items JSON"])
        self.assertEqual(items,[
            {"product":"Service A","unit_krw":110000,"qty":20,"net_krw":2200000},
            {"product":"Service B","unit_krw":190000,"qty":20,"net_krw":3800000},
        ])
        self.assertEqual(result["Product Net KRW"],6000000)
        self.assertEqual((result["Cloud Qty"],result["Cloud Net KRW"]),(3,105000))
        self.assertEqual((result["Quote Net KRW"],result["VAT KRW"],result["Quote Gross KRW"]),
                         (6105000,610500,6715500))
        self.assertEqual(result["Product Qty"],40)
        self.assertEqual(result["Product Unit KRW"],"")
        self.assertEqual(result["Sample Unit KRW"],"")
        self.assertEqual(set(result),set(PRICE_RESULT_FIELDS))
        self.assertEqual(result["Price Status"],"SOURCE_VERIFIED_MULTI_PRODUCT_PROJECTION")

    def test_original_total_reconciles(self):
        result=evaluate_multi(example_quote(),12,12.0)
        self.assertEqual((result["Cloud Qty"],result["Quote Net KRW"]),(2,3670000))

    def test_cloud_override_is_review_only(self):
        result=evaluate_multi(example_quote(),20,12.0,cloud_override="40000")
        self.assertEqual(result["Cloud Net KRW"],120000)
        self.assertEqual(result["Price Status"],"MANUAL_OVERRIDE_REVIEW_REQUIRED")

    def test_aggregate_override_forbidden(self):
        with self.assertRaisesRegex(PriceError,"MULTI_PRODUCT_AGGREGATE_OVERRIDE_FORBIDDEN"):
            evaluate_multi(example_quote(),20,12,product_override="300000")

    def test_unverified_source_rejected(self):
        q=example_quote();q["pricingStatus"]="PROCESS_BREAKDOWN_UNVERIFIED"
        with self.assertRaisesRegex(PriceError,"SOURCE_MULTI_PRODUCT_LINES_NOT_VERIFIED"):
            evaluate_multi(q,20,12)

    def test_product_id_collision_blocks(self):
        q=example_quote();q["sourceProductLines"][1]["productKey"]="lineA"
        with self.assertRaisesRegex(PriceError,"SOURCE_PRODUCT_IDENTITY_AMBIGUOUS"):
            evaluate_multi(q,20,12)

    def test_misaligned_product_process_net_blocks(self):
        q=example_quote();q["sourceProductLines"][1]["processPriceLines"][0]["sourceNetKrw"]=1
        with self.assertRaisesRegex(PriceError,"PROCESS_LINE_ARITHMETIC_MISMATCH"):
            evaluate_multi(q,20,12)

    def test_product_line_net_mismatch_blocks(self):
        q=example_quote();q["sourceProductLines"][1]["sourceNetKrw"]=1
        with self.assertRaisesRegex(PriceError,"SOURCE_PRODUCT_NET_MISMATCH"):
            evaluate_multi(q,20,12)

    def test_cloud_double_count_blocks(self):
        q=example_quote();q["cloudProcessLine"]["sourceNetKrw"]=140000
        with self.assertRaisesRegex(PriceError,"SOURCE_SHARED_CLOUD_MISMATCH"):
            evaluate_multi(q,20,12)

    def test_cloud_embedded_in_product_blocks(self):
        q=example_quote();q["sourceProductLines"][0]["processPriceLines"][0]["isCloud"]=True
        with self.assertRaisesRegex(PriceError,"SOURCE_PRODUCT_PROCESS_UNCLASSIFIED"):
            evaluate_multi(q,20,12)

    def test_source_total_mismatch_blocks(self):
        q=example_quote();q["totalPriceKrw"]=3700000
        with self.assertRaisesRegex(PriceError,"SOURCE_QUOTE_RECONCILIATION_FAILED"):
            evaluate_multi(q,20,12)

    def test_source_vat_mismatch_blocks(self):
        q=example_quote();q["grandTotalKrw"]=9999999
        with self.assertRaisesRegex(PriceError,"SOURCE_VAT_RECONCILIATION_FAILED"):
            evaluate_multi(q,20,12)

    def test_source_data_per_product_sum_must_match(self):
        q=example_quote();q["sourceProductLines"][1]["dataGbPerSample"]=8
        with self.assertRaisesRegex(PriceError,"PRODUCT_DATA_SIZE_SUM_MISMATCH"):
            evaluate_multi(q,20,12)

    def test_product_specific_quantity_changes_are_not_guessed(self):
        q=example_quote();q["sourceProductLines"][1]["sourceQty"]=10
        with self.assertRaisesRegex(PriceError,"MULTI_PRODUCT_DIFFERENT_QUANTITY_UNSUPPORTED"):
            evaluate_multi(q,20,12)

    def test_multi_never_calls_salesforce_ui_in_check_or_save(self):
        for mode in ("CHECK","SAVE"):
            with self.subTest(mode=mode):
                request=example_request(**{"Run Mode":mode})
                with patch("feishu_sfdc_local_worker.json_run",return_value=example_bundle()) as runner:
                    result=process(request)
                self.assertEqual(result["status"],"PREFLIGHT_BLOCK")
                self.assertEqual(result["code"],"MULTI_PRODUCT_QUOTE_FORM_NOT_VERIFIED")
                self.assertEqual(result["price_fields"]["Quote Net KRW"],6105000)
                self.assertEqual(runner.call_count,1)  # only catalog, not UI executor

    def test_real_reader_without_verified_lines_stays_blocked(self):
        bundle=example_bundle()
        bundle["linkedQuotes"][0]["pricingStatus"]="PROCESS_BREAKDOWN_UNVERIFIED"
        with patch("feishu_sfdc_local_worker.json_run",return_value=bundle):
            result=prepare_pair(example_request())
        self.assertEqual(result["status"],"PREFLIGHT_BLOCK")
        self.assertEqual(result["code"],"SOURCE_MULTI_PRODUCT_LINES_NOT_VERIFIED")


if __name__=="__main__":
    unittest.main()
