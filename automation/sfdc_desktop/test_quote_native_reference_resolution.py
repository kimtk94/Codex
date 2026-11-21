"""Synthetic reference resolver tests; no real Salesforce customer/pricing data."""
import unittest
from quote_native_reference_resolution import (
    resolve_report_process_id, resolve_native_data_unit, resolve_product_service,
    resolve_reference_status, resolve_2026_native_krw_product_signature,
    resolve_2026_native_krw_signature_by_report_geometry,
)

PID = "Process-2020-04-29-00039"
OTHER = "Process-2020-04-29-00031"


class NativeReferenceResolutionTests(unittest.TestCase):
    def test_master_name_matches_exact_report_id(self):
        self.assertEqual(resolve_report_process_id(
            {"Name": PID, "Process_ID__c": "GY0001"}, [PID, OTHER]), PID)

    def test_short_native_code_is_not_a_report_process_id(self):
        self.assertIsNone(resolve_report_process_id(
            {"Name": "Library preparation", "Process_ID__c": "GY0001"},
            [PID, OTHER]))

    def test_different_report_id_is_rejected(self):
        self.assertIsNone(resolve_report_process_id({"Name": OTHER}, [PID]))

    def test_conflicting_master_report_identifiers_block(self):
        self.assertIsNone(resolve_report_process_id(
            {"Name": PID, "Process_ID__c": OTHER}, [PID, OTHER]))

    def test_unknown_master_is_not_inferred_from_process_name(self):
        self.assertIsNone(resolve_report_process_id({}, [PID, OTHER]))
        self.assertIsNone(resolve_report_process_id(None, [PID]))

    def test_picklist_exact_label_maps_native_numeric_code(self):
        result = resolve_native_data_unit(
            "4", None, [{"value": "4", "label": "G raw data"}])
        self.assertEqual(result, "G raw data")

    def test_numeric_code_without_source_mapping_is_hold(self):
        self.assertIsNone(resolve_native_data_unit("4", None, []))
        self.assertIsNone(resolve_native_data_unit(
            "4", None, [{"value": "4", "label": "Unknown"}]))

    def test_conflicting_display_and_picklist_unit_blocks(self):
        self.assertIsNone(resolve_native_data_unit(
            "4", "M raw reads", [{"value": "4", "label": "G raw data"}]))

    def test_native_direct_unit_and_display_unit(self):
        self.assertEqual(resolve_native_data_unit(
            "G raw data", None, []), "G raw data")
        self.assertEqual(resolve_native_data_unit("4", "Gb", []), "Gb")

    def test_product_service_requires_native_name_not_geometry(self):
        self.assertEqual(resolve_product_service({"Name": "Synthetic Hi-C"}), "Synthetic Hi-C")
        self.assertIsNone(resolve_product_service({"Process Names": "Hi-C"}))

    def test_exact_quoted_product_process_membership(self):
        expected = [{"quotation_product_id": "QD-001", "process_id": PID},
                    {"quotation_product_id": "QD-002", "process_id": PID}]
        a = resolve_reference_status(resolved_process_rows=expected, expected_rows=expected,
             verified_service_labels=["Synthetic Hi-C", "Synthetic WGS"],
             expected_product_count=2)
        self.assertEqual(a["status"],
                         "SOURCE_REFERENCES_RESOLVED_RATE_PROMOTION_REQUIRES_REVIEW")
        self.assertEqual(a["original_process_rows_verified"], 2)
        self.assertFalse(a["historical_price_index_promoted"])
        self.assertFalse(a["save_permitted"])

    def test_missing_product_service_master_blocks(self):
        row = [{"quotation_product_id": "QD-001", "process_id": PID}]
        r = resolve_reference_status(resolved_process_rows=row, expected_rows=row,
             verified_service_labels=[""], expected_product_count=1)
        self.assertEqual(r["status"], "HOLD_PRODUCT_SERVICE_MASTER_UNRESOLVED")

    def test_report_process_assigned_to_wrong_product_blocks(self):
        actual = [{"quotation_product_id": "QD-002", "process_id": PID}]
        expected = [{"quotation_product_id": "QD-001", "process_id": PID}]
        r = resolve_reference_status(resolved_process_rows=actual,
             expected_rows=expected, verified_service_labels=["Synthetic WGS"],
             expected_product_count=1)
        self.assertEqual(r["status"], "HOLD_PROCESS_REFERENCE_ID_MISMATCH")

    def test_duplicate_original_process_identifier_blocks(self):
        row = {"quotation_product_id": "QD-001", "process_id": PID}
        r = resolve_reference_status(resolved_process_rows=[row,row],
             expected_rows=[row,row],verified_service_labels=["Synthetic Hi-C"],
             expected_product_count=1)
        self.assertEqual(r["status"], "HOLD_PROCESS_REFERENCE_ID_MISMATCH")


    def test_exact_native_service_signature_resolves_only_unique_krw(self):
        rows = [
            {"product_name":"Synthetic Hi-C", "product_signature":"SRC-P1",
             "currency":"KRW","was_usd_converted":False,
             "approval_status":"APPROVED","active":True,"created_date":"2026-06-11"},
            {"product_name":"Synthetic Hi-C", "product_signature":"SRC-P1",
             "currency":"KRW","was_usd_converted":False,
             "approval_status":"APPROVED","active":True,"created_date":"2026-08-11"},
            {"product_name":"Synthetic WGS", "product_signature":"SRC-P2",
             "currency":"KRW","was_usd_converted":False,
             "approval_status":"APPROVED","active":True,"created_date":"2026-08-11"}
        ]
        self.assertEqual(resolve_2026_native_krw_product_signature("Synthetic Hi-C",rows),
                         "SRC-P1")
        self.assertIsNone(resolve_2026_native_krw_product_signature("Hi-C",rows))

    def test_ambiguous_service_signatures_cannot_be_resolved_from_geometry(self):
        rows = [
            {"product_name":"Synthetic Hi-C", "product_signature":v,
             "currency":"KRW","was_usd_converted":False,
             "approval_status":"APPROVED","active":True,"created_date":"2026-08-11"}
            for v in ("SRC-P1","SRC-P2")
        ]
        self.assertIsNone(resolve_2026_native_krw_product_signature("Synthetic Hi-C",rows))

    def test_usd_converted_and_inactive_rate_cannot_supply_signature(self):
        row={"product_name":"Synthetic Hi-C", "product_signature":"SRC-P1",
             "currency":"USD","was_usd_converted":True,
             "approval_status":"APPROVED","active":True,"created_date":"2026-08-11"}
        self.assertIsNone(resolve_2026_native_krw_product_signature("Synthetic Hi-C",[row]))
        row["currency"]="KRW";row["was_usd_converted"]=False;row["active"]=False
        self.assertIsNone(resolve_2026_native_krw_product_signature("Synthetic Hi-C",[row]))



    def test_exact_service_plus_complete_process_geometry_resolves_variant(self):
        release = "Process-2020-04-29-00034"
        service = "Synthetic mRNA (WOBI)"
        def row(qid,signature,process,size,product=service,unit="G raw data"):
            return {"quote_id":qid,"product_signature":signature,
                "product_name":product,"process_id":process,"data_unit":unit,
                "data_size":size,"source_verified":True,
                "source_kind":"VERIFIED_SFDC_KRW_PROCESS_PRICE",
                "currency":"KRW","was_usd_converted":False,
                "vat_basis":"VAT_EXCLUDED","approval_status":"APPROVED",
                "active":True,"created_date":"2026-08-11"}
        correct=[
            row("Q-01","SRC-BASE",PID,"6"),
            row("Q-01","SRC-BASE",OTHER,"6"),
            row("Q-01","SRC-BASE",release,"1")
        ]
        other_size=[
            row("Q-02","SRC-OTHER",PID,"10"),
            row("Q-02","SRC-OTHER",OTHER,"10"),
            row("Q-02","SRC-OTHER",release,"1")
        ]
        other_service=[
            row("Q-03","SRC-WGS",PID,"6",product="Synthetic WGS"),
            row("Q-03","SRC-WGS",OTHER,"6",product="Synthetic WGS"),
            row("Q-03","SRC-WGS",release,"1",product="Synthetic WGS")
        ]
        report=[
            {"process_id":PID,"data_unit":"G raw data","data_size":"6"},
            {"process_id":OTHER,"data_unit":"Gb","data_size":"6.0"},
            {"process_id":release,"data_unit":"G raw data","data_size":"1"}
        ]
        get=resolve_2026_native_krw_signature_by_report_geometry
        self.assertEqual(get(service,report,correct+other_size+other_service),
                         "SRC-BASE")
        self.assertIsNone(get("Synthetic WGS Missing",report,correct))
        self.assertIsNone(get(service,report,other_service))

    def test_ambiguous_signatures_with_same_service_and_geometry_hold(self):
        def entry(qid,signature):
            return {"quote_id":qid,"product_signature":signature,
                "product_name":"Synthetic mRNA", "process_id":PID,
                "data_unit":"G raw data","data_size":"6",
                "source_verified":True,
                "source_kind":"VERIFIED_SFDC_KRW_PROCESS_PRICE",
                "currency":"KRW","was_usd_converted":False,
                "vat_basis":"VAT_EXCLUDED","approval_status":"APPROVED",
                "active":True,"created_date":"2026-08-11"}
        rows=[entry("Q-01","SRC-A"),entry("Q-02","SRC-B")]
        report=[{"process_id":PID,"data_unit":"Gb","data_size":"6.0"}]
        self.assertIsNone(resolve_2026_native_krw_signature_by_report_geometry(
            "Synthetic mRNA",report,rows))

    def test_invalid_process_units_or_ineligible_source_hold(self):
        row={"quote_id":"Q-01","product_signature":"SRC-A",
            "product_name":"Synthetic mRNA", "process_id":PID,
            "data_unit":"G raw data","data_size":"6",
            "source_verified":True,
            "source_kind":"VERIFIED_SFDC_KRW_PROCESS_PRICE",
            "currency":"KRW","was_usd_converted":False,
            "vat_basis":"VAT_EXCLUDED","approval_status":"APPROVED",
            "active":True,"created_date":"2026-08-11"}
        get=resolve_2026_native_krw_signature_by_report_geometry
        report=[{"process_id":PID,"data_unit":"Gb","data_size":"6"}]
        self.assertEqual(get("Synthetic mRNA",report,[row]),"SRC-A")
        for field,value in (("currency","USD"),("active",False),
                            ("was_usd_converted",True),("source_verified",False),
                            ("created_date","2025-08-11")):
            invalid={**row,field:value}
            self.assertIsNone(get("Synthetic mRNA",report,[invalid]))
        self.assertIsNone(get("Synthetic mRNA",[
            {"process_id":"GY0001","data_unit":"Gb","data_size":"6"}],[row]))
        self.assertIsNone(get("Synthetic mRNA",[
            {"process_id":PID,"data_unit":"4","data_size":"6"}],[row]))
        self.assertIsNone(get("Synthetic mRNA",[
            {"process_id":PID,"data_unit":"Gb","data_size":""}],[row]))

    def test_full_quote_group_required_not_eligible_subset(self):
        base={"quote_id":"Q-01","product_signature":"SRC-A",
            "product_name":"Synthetic mRNA", "data_unit":"Gb","data_size":"6",
            "source_verified":True,
            "source_kind":"VERIFIED_SFDC_KRW_PROCESS_PRICE",
            "currency":"KRW","was_usd_converted":False,
            "vat_basis":"VAT_EXCLUDED","approval_status":"APPROVED",
            "active":True,"created_date":"2026-08-11"}
        good={**base,"process_id":PID}
        extra={**base,"process_id":OTHER,"active":False}
        report=[{"process_id":PID,"data_unit":"Gb","data_size":"6"}]
        self.assertIsNone(resolve_2026_native_krw_signature_by_report_geometry(
            "Synthetic mRNA",report,[good,extra]))



if __name__ == "__main__":
    unittest.main()
