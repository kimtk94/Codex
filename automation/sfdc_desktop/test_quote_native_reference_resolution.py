"""Synthetic reference resolver tests; no real Salesforce customer/pricing data."""
import unittest
from quote_native_reference_resolution import (
    resolve_report_process_id, resolve_native_data_unit, resolve_product_service,
    resolve_reference_status,
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


if __name__ == "__main__":
    unittest.main()
