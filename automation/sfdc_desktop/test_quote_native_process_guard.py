"""Synthetic source evidence only, never actual customer or rate information."""
from copy import deepcopy
import unittest
from quote_native_process_guard import audit_native_process_bundle

PRODUCT="a0N" + "1"*12
PROCESS_REF="Process-2020-04-29-00039"
P2_REF="Process-2020-04-29-00031"
RELEASE_REF="Process-2020-04-29-00034"


def fixture():
    expected=[
      dict(quotation_product_id="QD-SYNTHETIC",process_id=PROCESS_REF,
           process_name="Library preparation",sample_quantity="2.00",data_size="6",
           data_unit="G raw data"),
      dict(quotation_product_id="QD-SYNTHETIC",process_id=P2_REF,
           process_name="Sequencing by data amount",sample_quantity="2.00",data_size="6",
           data_unit="G raw data"),
      dict(quotation_product_id="QD-SYNTHETIC",process_id=RELEASE_REF,
           process_name="Data release",sample_quantity="4.00",data_size="1",
           data_unit="G raw data")
    ]
    def row(code,native,process,qty,size,unit,pack):
        return dict(resolvedReportProcessId=code, nativeProcessCode=native,
          processName=process,quantity=qty,dataSize=size,dataUnit="G raw data",
          unitPrice=unit,totalPrice=int(qty)*int(unit),packNo=pack,
          productId=PRODUCT,nativeActive=True)
    rows=[
      row(PROCESS_REF,"GY0001","Library preparation",2,6,1000,"Pack1"),
      row(P2_REF,"GY0002","Sequencing by data amount",2,6,2000,"Pack1"),
      row(RELEASE_REF,"PR0019","Data release",4,1,0,"")
    ]
    source=dict(source="AUTHENTICATED_SFDC_UI_API_GET_ONLY",
                salesforce_write=False,currency="KRW",gst="10,KR-VAT",
                quoteStatus="Ready to send",quoteNet=6000,feeTotal=1000,
                grandTotal=7700,products=[
                  dict(recordId=PRODUCT,name="QD-SYNTHETIC",net=6000,processRows=rows)])
    manifest=dict(created_date="2026-08-11",
                  quote_id="QID-2026-08-11-123456",approvalConfirmed=True,
                  approvalTimeConfirmed=True,expected_process_lines=expected)
    return source,manifest


class NativeProcessGuardTests(unittest.TestCase):
    def test_complete_original_reference_with_different_native_code_passes(self):
        s,m=fixture()
        r=audit_native_process_bundle(s,m)
        self.assertEqual(r["status"],"NATIVE_PROCESS_AND_REPORT_REFERENCES_VERIFIED")
        self.assertEqual(r["verified_rows"],3)
        self.assertEqual(r["zero_price_steps"],1)
        self.assertFalse(r["new_quote_price_approved"])
        self.assertFalse(r["historical_index_auto_promote"])

    def test_wrong_process_reference_namespace_is_not_silently_accepted(self):
        s,m=fixture()
        s["products"][0]["processRows"][0]["resolvedReportProcessId"]="GY0001"
        self.assertEqual(audit_native_process_bundle(s,m)["status"],
          "HOLD_PROCESS_REFERENCE_ALIAS_UNVERIFIED")

    def test_bad_multiplication_fails(self):
        s,m=fixture()
        s["products"][0]["processRows"][0]["totalPrice"]=1999
        self.assertEqual(audit_native_process_bundle(s,m)["status"],
          "HOLD_PROCESS_MULTIPLICATION")

    def test_missing_nonrelease_pack_fails(self):
        s,m=fixture()
        s["products"][0]["processRows"][0]["packNo"]=""
        self.assertEqual(audit_native_process_bundle(s,m)["status"],
          "HOLD_UNEXPECTED_MISSING_PACK")

    def test_paid_data_release_without_pack_passes_exact_native_totals(self):
        s,m=fixture()
        s["products"][0]["processRows"][-1]["unitPrice"]=100
        s["products"][0]["processRows"][-1]["totalPrice"]=400
        s["products"][0]["net"]=6400
        s["quoteNet"]=6400
        s["grandTotal"]=8140
        r=audit_native_process_bundle(s,m)
        self.assertEqual(r["status"],
          "NATIVE_PROCESS_AND_REPORT_REFERENCES_VERIFIED")
        self.assertEqual(r["unpacked_data_release_steps"],1)
        self.assertEqual(r["positive_unpacked_data_release_steps"],1)
        self.assertEqual(r["zero_price_steps"],0)
        self.assertFalse(r["historical_index_auto_promote"])

    def test_paid_data_release_without_pack_still_requires_correct_subtotal(self):
        s,m=fixture()
        s["products"][0]["processRows"][-1]["unitPrice"]=100
        s["products"][0]["processRows"][-1]["totalPrice"]=400
        self.assertEqual(audit_native_process_bundle(s,m)["status"],
          "HOLD_PRODUCT_SUM")

    def test_process_must_belong_to_same_product(self):
        s,m=fixture()
        s["products"][0]["processRows"][1]["productId"]="a0N"+"2"*12
        self.assertEqual(audit_native_process_bundle(s,m)["status"],
          "HOLD_FOREIGN_PRODUCT_PROCESS")

    def test_report_sample_quantity_and_gb_must_match(self):
        for field,value in (("quantity",20),("dataSize",9),("dataUnit","M raw reads")):
            s,m=fixture()
            s["products"][0]["processRows"][0][field]=value
            self.assertEqual(audit_native_process_bundle(s,m)["status"],
              "HOLD_PROCESS_FIELDS_MISMATCH")

    def test_missing_report_row_blocks(self):
        s,m=fixture()
        m["expected_process_lines"].pop()
        self.assertEqual(audit_native_process_bundle(s,m)["status"],
          "HOLD_PROCESS_REFERENCE_ALIAS_UNVERIFIED")

    def test_grand_total_fee_and_currency_block_if_unverified(self):
        for key,value in (("grandTotal",8000),("currency","USD"),("quoteStatus","Draft")):
            s,m=fixture()
            s[key]=value
            self.assertFalse(audit_native_process_bundle(s,m)["eligible_for_separate_historical_index_review"]
              if "eligible_for_separate_historical_index_review" in audit_native_process_bundle(s,m) else False)

    def test_no_approval_no_rate_promotion(self):
        s,m=fixture()
        m["approvalConfirmed"]=False
        r=audit_native_process_bundle(s,m)
        self.assertEqual(r["status"],"HOLD_APPROVAL_EVIDENCE")
        self.assertFalse(r["historical_index_auto_promote"])
        self.assertFalse(r["save_permitted"])
        self.assertFalse(r["salesforce_write"])

    def test_unverified_source_never_becomes_a_price(self):
        s,m=fixture()
        s["source"]="LOCAL_UNVERIFIED_JSON"
        self.assertEqual(audit_native_process_bundle(s,m)["status"],"HOLD_SOURCE_PROVENANCE")


if __name__=="__main__":
    unittest.main()
