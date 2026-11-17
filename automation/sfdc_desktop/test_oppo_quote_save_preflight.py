"""Synthetic-only tests: never call Salesforce or store real customer data."""
import copy
from datetime import datetime, timezone, timedelta
import unittest
from oppo_quote_save_preflight import audit_save_preflight

ASOF = datetime(2026, 11, 17, 14, 55, tzinfo=timezone.utc)
ACCOUNT = "001000000000001"
CONTACT = "003000000000001"
PRODUCT = "a0F000000000001"


def fixture():
    candidate = {
        "operation": "CREATE_NEW_OPPORTUNITY_AND_QUOTATION",
        "opportunity_name": "Korea-Synthetic-RNA-48samples",
        "quotation_name": "Korea-Synthetic-RNA-48samples",
        "country": "Korea", "account_id": ACCOUNT, "contact_id": CONTACT,
        "request_date_kst": "2026-11-17", "close_date_kst": "2026-12-17",
        "currency": "KRW", "vat_rate": "0.10",
        "stage": "Prospective", "forecast_category": "Pipeline",
        "service_line": "RNA-seq",
        "description": "Synthetic 48 samples expected; quote requested; PO unconfirmed.",
        "source_progress_description": "Synthetic old source status unrelated.",
        "sample_quantity": 48,
        "products": [{
            "native_product_id": PRODUCT,
            "product_name": "Synthetic mRNA service",
            "source_reference_only": True,
            "processes": [
                {
                    "process_id": "Process-2020-01-01-00001",
                    "native_process_id": "a1B000000000001",
                    "process_category": "LIBRARY",
                    "new_process_quantity": "48",
                    "new_unit_price_krw": "50000",
                    "new_production_depth": "6",
                    "data_unit": "Gb",
                    "current_native_price_rechecked": True,
                    "pack_applicable": True, "pack_verified": True,
                }, {
                    "process_id": "Process-2020-01-01-00002",
                    "native_process_id": "a1B000000000002",
                    "process_category": "SEQUENCING",
                    "new_process_quantity": "48",
                    "new_unit_price_krw": "150000",
                    "new_production_depth": "6",
                    "data_unit": "Gb",
                    "current_native_price_rechecked": True,
                    "pack_applicable": True, "pack_verified": True,
                }, {
                    "process_id": "Process-2020-01-01-00003",
                    "native_process_id": "a1B000000000003",
                    "process_category": "ALICLOUD",
                    "new_process_quantity": "3",
                    "new_unit_price_krw": "30000",
                    "new_production_depth": "288",
                    "data_unit": "Gb",
                    "current_native_price_rechecked": True,
                    "pack_applicable": False, "pack_verified": False,
                },
            ],
        }],
        "cloud": {"required": True, "total_gb": "288",
                  "amount_included_in_process_rows": True},
        "quote_fee": {"mode": "EXCLUDE", "amount_krw": "0"},
        "expected_net_krw": "9690000",
        "opportunity_amount_krw": "9690000",
    }
    evidence = {
        "source": "AUTHENTICATED_SFDC_UI_READ_ONLY",
        "salesforce_write": False,
        "checked_at_utc": "2026-11-17T14:54:00Z",
        "account_id": ACCOUNT, "contact_id": CONTACT,
        "account_contact_relation_verified": True,
        "opportunity_record_type_verified": True,
        "stage_and_forecast_verified": True,
        "service_line_verified": True,
        "current_product_and_process_ids_verified": True,
        "current_native_krw_rates_verified": True,
        "per_process_pack_rules_verified": True,
        "client_price_condition_approved": True,
        "opportunity_amount_field_verified": True,
        "opportunity_quote_schema_verified": True,
        "quote_fee_mode_verified": True,
        "cloud_required_and_allocation_verified": True,
        "duplicate_check": {"scope": "ACCOUNT_CONTACT_NAME",
                            "matching_opportunities": 0, "matching_quotations": 0},
    }
    return candidate, evidence


class SavePreflightTests(unittest.TestCase):
    def audit(self, c, e):
        return audit_save_preflight(c, e, asof_utc=ASOF)

    def test_all_synthetic_sources_ready_for_human_approval_never_save(self):
        c, e = fixture()
        result = self.audit(c, e)
        self.assertEqual(result["status"], "READY_FOR_PER_RECORD_OPERATOR_APPROVAL")
        self.assertEqual(result["expected_net_krw"], "9690000")
        self.assertEqual(result["expected_vat_krw"], "969000.00")
        self.assertEqual(result["expected_gross_krw"], "10659000.00")
        self.assertEqual(result["verified_product_count"], 1)
        self.assertEqual(result["verified_process_row_count"], 3)
        self.assertTrue(result["ready_for_review"])
        self.assertFalse(result["salesforce_save_permitted"])
        self.assertFalse(result["opportunity_created"])
        self.assertFalse(result["quotation_created"])
        self.assertEqual(result["crm_writes"], 0)

    def test_approval_digest_changes_with_one_price_or_quantity(self):
        c, e = fixture()
        baseline = self.audit(c, e)["approval_digest"]
        changed = copy.deepcopy(c)
        changed["products"][0]["processes"][0]["new_unit_price_krw"] = "60000"
        changed["expected_net_krw"] = "10170000"
        changed["opportunity_amount_krw"] = "10170000"
        self.assertNotEqual(baseline, self.audit(changed, e)["approval_digest"])
        self.assertEqual(self.audit(changed, e)["status"],
                         "READY_FOR_PER_RECORD_OPERATOR_APPROVAL")

    def test_old_source_evidence_blocks(self):
        c, e = fixture()
        e["checked_at_utc"] = "2026-11-16T14:54:00Z"
        self.assertIn("READBACK_STALE", self.audit(c, e)["reason_codes"])

    def test_future_readback_blocks(self):
        c, e = fixture()
        e["checked_at_utc"] = "2026-11-18T14:54:00Z"
        self.assertIn("READBACK_STALE", self.audit(c, e)["reason_codes"])

    def test_same_name_existing_opportunity_or_quote_blocks(self):
        for kind in ("matching_opportunities", "matching_quotations"):
            c, e = fixture()
            e["duplicate_check"][kind] = 1
            self.assertIn("DUPLICATE_OR_AMBIGUOUS_EXISTING_RECORD",
                          self.audit(c, e)["reason_codes"])

    def test_no_authenticated_account_contact_relation_blocks(self):
        c, e = fixture()
        e["account_contact_relation_verified"] = False
        self.assertIn("UNVERIFIED_ACCOUNT_CONTACT_RELATION_VERIFIED",
                      self.audit(c, e)["reason_codes"])

    def test_wrong_account_contact_cannot_be_inferred_from_historical_quote(self):
        c, e = fixture()
        c["contact_id"] = "003000000000002"
        self.assertIn("ACCOUNT_CONTACT_SOURCE_MISMATCH", self.audit(c, e)["reason_codes"])

    def test_currency_and_country_are_native_krw_korea(self):
        c, e = fixture()
        c["currency"] = "USD"
        c["country"] = "Hong Kong"
        codes = self.audit(c, e)["reason_codes"]
        self.assertIn("CURRENCY_OR_VAT_RATE", codes)
        self.assertIn("COUNTRY_UNVERIFIED", codes)

    def test_quote_and_opportunity_names_must_match(self):
        c, e = fixture()
        c["quotation_name"] = "Another quote"
        self.assertIn("OPPORTUNITY_QUOTE_NAME_MISMATCH",
                      self.audit(c, e)["reason_codes"])

    def test_close_date_plus_one_calendar_month(self):
        c, e = fixture()
        c["close_date_kst"] = "2026-12-18"
        self.assertIn("CLOSE_DATE_NOT_PLUS_ONE_MONTH",
                      self.audit(c, e)["reason_codes"])

    def test_progress_description_cannot_clone_old_source(self):
        c, e = fixture()
        c["description"] = c["source_progress_description"]
        self.assertIn("PROGRESS_DESCRIPTION_COPIED",
                      self.audit(c, e)["reason_codes"])

    def test_missing_native_product_process_or_pack_blocks(self):
        c, e = fixture()
        c["products"][0]["native_product_id"] = ""
        c["products"][0]["processes"][0]["native_process_id"] = ""
        c["products"][0]["processes"][0]["pack_verified"] = False
        codes = self.audit(c, e)["reason_codes"]
        self.assertIn("NATIVE_PRODUCT_ID_MISSING", codes)
        self.assertIn("NATIVE_PROCESS_ID_MISSING", codes)
        self.assertIn("PACK_UNVERIFIED", codes)

    def test_price_current_native_source_must_be_rechecked(self):
        c, e = fixture()
        c["products"][0]["processes"][0]["current_native_price_rechecked"] = False
        self.assertIn("PRICE_SOURCE_RECHECK_REQUIRED", self.audit(c, e)["reason_codes"])

    def test_process_quantity_and_price_fail_closed(self):
        for value in ("0", "-1", "4.00001", "nan", "50000USD"):
            c, e = fixture()
            c["products"][0]["processes"][0]["new_unit_price_krw"] = value
            if value == "0":
                # Native zero-priced bundled Process is legitimate, not absent.
                c["expected_net_krw"] = "7290000"
                c["opportunity_amount_krw"] = "7290000"
                self.assertTrue(self.audit(c, e)["ready_for_review"])
            else:
                self.assertIn("PROCESS_QUANTITY_PRICE_INVALID",
                              self.audit(c, e)["reason_codes"])
        c, e = fixture()
        c["products"][0]["processes"][0]["new_process_quantity"] = "0"
        self.assertIn("PROCESS_QUANTITY_PRICE_INVALID",
                      self.audit(c, e)["reason_codes"])

    def test_alicloud_ceil_100_gb_and_no_double_counting(self):
        c, e = fixture()
        c["products"][0]["processes"][2]["new_process_quantity"] = "2"
        self.assertIn("ALICLOUD_QTY_MISMATCH", self.audit(c, e)["reason_codes"])
        c, e = fixture()
        c["cloud"]["amount_included_in_process_rows"] = False
        self.assertIn("ALICLOUD_PRICE_ALLOCATION_UNVERIFIED",
                      self.audit(c, e)["reason_codes"])

    def test_fee_default_zero_separate_from_product_processes(self):
        c, e = fixture()
        c["quote_fee"]["mode"] = "EXCLUDE"
        c["quote_fee"]["amount_krw"] = "30000"
        self.assertIn("EXCLUDED_FEE_MUST_BE_ZERO",
                      self.audit(c, e)["reason_codes"])

    def test_opportunity_amount_and_vat_excluded_quote_net_match(self):
        c, e = fixture()
        c["opportunity_amount_krw"] = "10659000"
        self.assertIn("OPPORTUNITY_AMOUNT_NOT_RECONCILED",
                      self.audit(c, e)["reason_codes"])

    def test_fractional_native_krw_rate_holds_even_when_total_readable(self):
        c, e = fixture()
        c["products"][0]["processes"][0]["new_unit_price_krw"] = "50000.0001"
        c["expected_net_krw"] = "9690000.0048"
        c["opportunity_amount_krw"] = "9690000.0048"
        self.assertIn("FRACTIONAL_KRW_TOTAL", self.audit(c, e)["reason_codes"])

    def test_each_quote_save_requires_fresh_duplicate_recheck_and_specific_approval(self):
        c, e = fixture()
        result = self.audit(c, e)
        self.assertTrue(result["operator_final_approval_required"])
        self.assertFalse(result["salesforce_save_permitted"])
        self.assertTrue(result["approval_digest"].startswith("SFDC-REVIEW-"))


if __name__ == "__main__":
    unittest.main()
