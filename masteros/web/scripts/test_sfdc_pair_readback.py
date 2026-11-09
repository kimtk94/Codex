"""Independent new-parent Quote readback tests; all Salesforce records synthetic."""
import copy
import unittest
from unittest.mock import patch

from sfdc_pair_readback import verify_saved_pair
from feishu_sfdc_local_worker import prepare_pair

SOURCE_OPPO = "006000000000000AAA"
SOURCE_QUOTE = "a0P000000000000AAA"
NEW_OPPO = "006000000000000AAB"
NEW_QUOTE = "a0P000000000000AAB"


def source_bundle():
    return {"status":"PASS","selectionStatus":"EXACT_ONE",
        "opportunity":{"id":SOURCE_OPPO,"name":"Reference-42",
            "accountId":"001000000000000AAA","contactId":"003000000000000AAA",
            "accountName":"Example Univ","contactName":"Example Contact"},
        "linkedQuotes":[{"id":SOURCE_QUOTE,"opportunityId":SOURCE_OPPO,
            "pricingStatus":"VERIFIED_PROCESS_LINES","sourceVatRateVerified10Pct":True,
            "cloudLinePresent":True,"productCount":1,"dataSize":12.0,
            "samples":42,"sourceCloudUnits":6,"totalPriceKrw":8190000,
            "sampleUnitNetKrw":190000,"cloudUnitNetKrw":35000,
            "productName":"Existing RNA Product","productCategory":"RNA",
            "processNames":"Preparation,AliCloud",
            "processPriceLines":[
                {"processName":"Preparation","unitPriceKrw":190000,"sourceQty":42,
                    "sourceNetKrw":7980000,"isCloud":False},
                {"processName":"AliCloud","unitPriceKrw":35000,"sourceQty":6,
                    "sourceNetKrw":210000,"isCloud":True}
            ]}]}


def expected():
    with patch("feishu_sfdc_local_worker.json_run",return_value=source_bundle()):
        return prepare_pair({"Source Oppo ID":SOURCE_OPPO,
            "Source Quote ID":SOURCE_QUOTE,
            "New Opportunity Name":"New-12",
            "New Samples":"12","Data Size Gb":"12"})


def live(prepared):
    base=source_bundle()["opportunity"]
    opp={**base,"id":NEW_OPPO,"name":prepared["opportunity"]["opportunityName"],
         "samples":12,"samplesSource":"SFDC_FIELD",
         "amountKrw":2350000,
         "progressDescriptionSource":prepared["opportunity"]["progressDescription"],
         "source":"LIVE_SALESFORCE","read_only":True}
    q=copy.deepcopy(source_bundle()["linkedQuotes"][0])
    q.update({"id":NEW_QUOTE,"opportunityId":NEW_OPPO,
        "name":prepared["quotation"]["quoteName"],
        "samples":12,"sourceCloudUnits":2,
        "totalPriceKrw":2350000,"grandTotalKrw":2585000,
        "accountId":base["accountId"],"contactId":base["contactId"],
        "accountName":base["accountName"],"contactName":base["contactName"],
        "source":"LIVE_SALESFORCE","read_only":True})
    q["processPriceLines"][0].update({"sourceQty":12,"sourceNetKrw":2280000})
    q["processPriceLines"][1].update({"sourceQty":2,"sourceNetKrw":70000})
    return {"status":"PASS","read_only":True,"selectionStatus":"EXACT_ONE",
        "opportunity":opp,"linkedQuotes":[q]}


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.prepared=expected()
        self.assertEqual(self.prepared["status"],"READY")
        self.bundle=live(self.prepared)

    def verify(self):
        return verify_saved_pair(self.prepared,NEW_OPPO,self.bundle)

    def test_exact_new_parent_and_price_readback(self):
        r=self.verify()
        self.assertEqual(r["status"],"PASS")
        self.assertEqual(r["code"],"NEW_OPPORTUNITY_QUOTE_INDEPENDENT_READBACK")
        self.assertEqual((r["net_krw"],r["gross_krw"],r["cloud_qty"]),(2350000,2585000,2))
        self.assertFalse(r["salesforce_write"])

    def test_old_opportunity_id_refused(self):
        r=verify_saved_pair(self.prepared,SOURCE_OPPO,self.bundle)
        self.assertEqual(r["code"],"NEW_PARENT_ID_NOT_VERIFIED")

    def test_quote_attached_to_source_parent_refused(self):
        self.bundle["linkedQuotes"][0]["opportunityId"]=SOURCE_OPPO
        self.assertEqual(self.verify()["code"],"NEW_QUOTE_PARENT_MISMATCH")

    def test_unchanged_source_quote_refused(self):
        self.bundle["linkedQuotes"][0]["id"]=SOURCE_QUOTE
        self.assertEqual(self.verify()["code"],"NEW_QUOTE_PARENT_MISMATCH")

    def test_two_new_quotes_ambiguous(self):
        self.bundle["linkedQuotes"].append(copy.deepcopy(self.bundle["linkedQuotes"][0]))
        self.assertEqual(self.verify()["code"],"NEW_PARENT_LINK_NOT_UNIQUE")

    def test_customer_contact_drift(self):
        self.bundle["linkedQuotes"][0]["contactId"]="003000000000000AAC"
        self.assertEqual(self.verify()["code"],"NEW_PAIR_CUSTOMER_MISMATCH")

    def test_missing_source_stamp_rejected(self):
        self.bundle["linkedQuotes"][0]["source"]=""
        self.assertEqual(self.verify()["code"],"INDEPENDENT_UI_SOURCE_UNVERIFIED")

    def test_duplicate_opportunity_name_rejected(self):
        self.bundle["opportunity"]["name"]="Reference-42"
        self.assertEqual(self.verify()["code"],"NEW_PAIR_NAMES_MISMATCH")

    def test_progress_was_copied_not_rebuilt(self):
        self.bundle["opportunity"]["progressDescriptionSource"]="Copied prior progress"
        self.assertEqual(self.verify()["code"],"NEW_PROGRESS_NOT_REPLACED")

    def test_estimated_sample_qty_from_name_not_enough(self):
        self.bundle["opportunity"]["samplesSource"]="OPPO_NAME_ESTIMATE"
        self.assertEqual(self.verify()["code"],"NEW_OPPORTUNITY_SAMPLE_UNVERIFIED")

    def test_wrong_opportunity_net(self):
        self.bundle["opportunity"]["amountKrw"]=1
        self.assertEqual(self.verify()["code"],"NEW_OPPORTUNITY_NET_MISMATCH")

    def test_wrong_quote_vat(self):
        self.bundle["linkedQuotes"][0]["grandTotalKrw"]=1
        self.assertEqual(self.verify()["code"],"NEW_QUOTE_VAT_TOTAL_MISMATCH")

    def test_changed_cloud_blocks(self):
        self.bundle["linkedQuotes"][0]["sourceCloudUnits"]=3
        self.assertEqual(self.verify()["code"],"NEW_QUOTE_PROCESS_RECONCILIATION_FAILED")

    def test_incomplete_live_product_breakdown(self):
        self.bundle["linkedQuotes"][0]["pricingStatus"]="REVIEW_REQUIRED"
        self.assertEqual(self.verify()["code"],"NEW_PRODUCT_IDENTITY_UNVERIFIED")

    def test_price_rate_mutation_refused(self):
        self.bundle["linkedQuotes"][0]["processPriceLines"][0]["unitPriceKrw"]=120000
        self.assertEqual(self.verify()["code"],"NEW_QUOTE_PROCESS_RECONCILIATION_FAILED")

    def test_quote_data_requirement_changed(self):
        self.bundle["linkedQuotes"][0]["dataSize"]=15.0
        self.assertEqual(self.verify()["code"],"NEW_QUOTE_QUANTITY_UNVERIFIED")

    def test_manual_override_does_not_silently_pass(self):
        self.prepared["price_fields"]["Price Status"]="MANUAL_OVERRIDE_REVIEW_REQUIRED"
        self.assertEqual(self.verify()["code"],"OVERRIDE_REQUIRES_SEPARATE_APPROVAL")

    def test_missing_live_bundle_blocks(self):
        self.bundle=None
        self.assertEqual(self.verify()["code"],"LIVE_BUNDLE_UNAVAILABLE")


if __name__=="__main__":
    unittest.main()
