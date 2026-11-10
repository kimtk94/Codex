import unittest
from unittest.mock import patch
from sfdc_record_catalog import check, parse_money, parse_us_date, rec_id, find_href, read_multi_product_evidence

class CatalogValidationTests(unittest.TestCase):
    def test_query_validation(self):
        self.assertEqual(check({"mode":"list","resource":"lead","query":"김지훈"})["resource"],"lead")
        with self.assertRaisesRegex(ValueError,"INVALID_SEARCH"):
            check({"mode":"list","resource":"lead","query":"x"*101})
        with self.assertRaisesRegex(ValueError,"INVALID_OPERATION"):
            check({"mode":"list","resource":"user","query":""})
    def test_force_live_requires_read_only_detail(self):
        self.assertTrue(check({"mode":"detail","resource":"quote","recordId":"a0P000000000000AAA","forceLive":True})["forceLive"])
        with self.assertRaisesRegex(ValueError,"LIVE_MODE_DETAIL_REQUIRED"):
            check({"mode":"bundle","resource":"opportunity","recordId":"006000000000000AAA","forceLive":True})
        with self.assertRaisesRegex(ValueError,"LIVE_FLAG_INVALID"):
            check({"mode":"detail","resource":"quote","recordId":"a0P000000000000AAA","forceLive":"yes"})
    def test_ids(self):
        self.assertTrue(rec_id("006000000000000AAA","006"))
        self.assertFalse(rec_id("00Q000000000000AAA","006"))
        self.assertFalse(rec_id("not-id","00Q"))
    def test_link(self):
        x=find_href([{"href":"/lightning/r/Contact/003TK00001L2RfnYAF/view","text":"Kim"}],"003")
        self.assertEqual(x["id"],"003TK00001L2RfnYAF")
    def test_numeric(self):
        self.assertEqual(parse_money("KRW 8,400,000.00"),8400000)
        self.assertEqual(parse_us_date("9/29/2026"),"2026-09-29")

    def test_multi_product_detail_proof_is_not_process_price_proof(self):
        source=[
            {"productName":"A","samples":12,"dataSize":5,"sourceLineNetKrw":1200000,
             "processNames":"Library A"},
            {"productName":"B","samples":12,"dataSize":7,"sourceLineNetKrw":2400000,
             "processNames":"Library B"},
        ]
        with patch("sfdc_record_catalog.source_quote_product",side_effect=source) as fetch:
            with patch("sfdc_record_catalog.hyperlinks",return_value=[
                {"text":"Parent","href":"/lightning/r/Quotation__c/a0P000000000000AAA/view"}]):
                result=read_multi_product_evidence(object(),"a0P000000000000AAA",
                    ["a0N000000000000AAA","a0N000000000000AAB"])
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]["productName"],"A")
        self.assertEqual(result[1]["dataGbPerSample"],7)
        self.assertEqual(fetch.call_count,2)
        self.assertTrue(all(x["evidenceStatus"]=="PRODUCT_DETAIL_ONLY_NO_PROCESS_PRICE_MAPPING" for x in result))
        self.assertTrue(all("processPriceLines" not in x for x in result))

    def test_multi_quote_parent_link_mismatch_blocks(self):
        with patch("sfdc_record_catalog.source_quote_product",return_value={
            "productName":"A","samples":10,"dataSize":5,"sourceLineNetKrw":1000}):
            with patch("sfdc_record_catalog.hyperlinks",return_value=[
                {"text":"Wrong","href":"/lightning/r/Quotation__c/a0P000000000000AAB/view"}]):
                with self.assertRaisesRegex(ValueError,"SOURCE_PRODUCT_PARENT_UNVERIFIED"):
                    read_multi_product_evidence(object(),"a0P000000000000AAA",
                        ["a0N000000000000AAA","a0N000000000000AAB"])

    def test_multi_duplicate_child_link_blocks(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_PRODUCT_LINKS_NOT_UNIQUE"):
            read_multi_product_evidence(object(),"a0P000000000000AAA",
                ["a0N000000000000AAA","a0N000000000000AAA"])

    def test_multi_missing_source_amount_blocks(self):
        with patch("sfdc_record_catalog.source_quote_product",return_value={
            "productName":"A","samples":10,"dataSize":5,"sourceLineNetKrw":0}):
            with patch("sfdc_record_catalog.hyperlinks",return_value=[
                {"text":"Parent","href":"/lightning/r/Quotation__c/a0P000000000000AAA/view"}]):
                with self.assertRaisesRegex(ValueError,"SOURCE_PRODUCT_FIELDS_INCOMPLETE"):
                    read_multi_product_evidence(object(),"a0P000000000000AAA",
                        ["a0N000000000000AAA","a0N000000000000AAB"])

if __name__=="__main__":unittest.main()
