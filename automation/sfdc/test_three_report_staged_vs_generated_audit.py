"""Independent SFDC source report / generated sink parity tests. No CRM credentials."""
import copy
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from three_report_staged_vs_generated_audit import (
    audit_source, compare_readback, evaluate, expected_relation, parse,
)


def fixture():
    leads = [{"SFDC Lead ID": "Lead-1"}, {"SFDC Lead ID": "Lead-2"}]
    opportunities = [{"Opportunity ID": "Opp-1"}, {"Opportunity ID": "Opp-2"}]
    quotations = [
        {"SFDC Quotation ID": "QID-1", "Opportunity ID": "Opp-1", "Quotation Product ID": "P1"},
        {"SFDC Quotation ID": "QID-1", "Opportunity ID": "Opp-1", "Quotation Product ID": "P2"},
        {"SFDC Quotation ID": "QID-2", "Opportunity ID": "", "Quotation Product ID": "P3"},
        {"SFDC Quotation ID": "QID-3", "Opportunity ID": "Opp-999", "Quotation Product ID": "P4"},
        {"SFDC Quotation ID": "QID-4", "Opportunity ID": "Opp-2", "Quotation Product ID": "P5"},
        {"SFDC Quotation ID": "QID-4", "Opportunity ID": "Opp-2", "Quotation Product ID": "P6"},
    ]
    audit = []
    for name, count, distinct, dup in (("Leads", 2, 2, 0),
                                      ("Opportunities", 2, 2, 0),
                                      ("Quotation", 6, 4, 2)):
        audit.append({"Entity": name, "Rows": str(count), "Unique IDs": str(distinct),
                      "Duplicate IDs": str(dup), "Missing IDs": "0",
                      "State": "PRESERVED_NO_NEW_REPORT",
                      "Source Received KST": "2026-11-08 17:00:00 KST",
                      "Ingest Checked KST": "2026-11-09 00:30:00 KST"})
    verified = [
        {"Quotation ID": "QID-1", "Opportunity ID": "Opp-1", "Quote Process Rows": "2",
         "Relation State": "QUOTE_OPPORTUNITY_ID_VERIFIED_NOT_REVENUE"},
        {"Quotation ID": "QID-4", "Opportunity ID": "Opp-2", "Quote Process Rows": "2",
         "Relation State": "QUOTE_OPPORTUNITY_ID_VERIFIED_NOT_REVENUE"},
    ]
    review = [
        {"Quotation ID": "QID-2", "Quote Process Rows": "1",
         "Distinct Opportunity IDs": "0", "Opportunity ID Missing Rows": "1",
         "Opportunity IDs Not In Export": "0",
         "Reason": "MISSING_OPPORTUNITY_ID | MULTIPLE_OR_ZERO_OPPORTUNITY_IDS",
         "Review State": "NEEDS_REVIEW"},
        {"Quotation ID": "QID-3", "Quote Process Rows": "1",
         "Distinct Opportunity IDs": "1", "Opportunity ID Missing Rows": "0",
         "Opportunity IDs Not In Export": "1",
         "Reason": "OPPORTUNITY_NOT_IN_EXPORT", "Review State": "NEEDS_REVIEW"},
    ]
    return {
        "SFDC Email Leads Raw": leads,
        "SFDC Email Opportunities Raw": opportunities,
        "SFDC Email Quotation Raw": quotations,
        "SFDC Verified Relations": verified,
        "SFDC Quote Link Review": review,
        "SFDC Email Ingest Audit": audit,
    }


class TestReportStageSinkParity(unittest.TestCase):
    def test_process_rows_are_not_duplicate_quotes(self):
        data = fixture()
        report = evaluate(data, dt.datetime(2026, 11, 9, tzinfo=dt.timezone.utc))
        self.assertEqual(report["source"]["quote_process_rows"], 6)
        self.assertEqual(report["source"]["unique_quotes"], 4)
        self.assertEqual(report["source"]["quotation_extra_process_rows_not_duplicate_quotes"], 2)
        self.assertEqual(report["sink"]["report_to_generated_readback_status"],
                         "PASS_STAGE_TO_GENERATED_ONLY")
        self.assertFalse(report["sfdc_save_certified"])
        self.assertEqual(report["sf_object_readback"], "SOURCE_UNAVAILABLE")

    def test_missing_opp_and_outside_export_are_not_claimed_deleted(self):
        report = evaluate(fixture())
        self.assertEqual(report["relation_exception_reasons"], {
            "MISSING_OPPORTUNITY_ID": 1,
            "MULTIPLE_OR_ZERO_OPPORTUNITY_IDS": 1,
            "OPPORTUNITY_NOT_IN_EXPORT": 1})
        self.assertEqual(report["sink"]["expected_review_quote_ids"], 2)
        self.assertEqual(report["sink"]["expected_verified_quote_ids"], 2)

    def test_stale_sink_quote_id_blocks(self):
        data = fixture()
        data["SFDC Verified Relations"].pop()
        result = evaluate(data)
        self.assertEqual(result["sink"]["report_to_generated_readback_status"], "SINK_LAG")
        self.assertEqual(result["sink"]["source_quote_ids_missing_in_sink"], 1)

    def test_wrong_opp_id_in_sink_blocks(self):
        data = fixture()
        data["SFDC Verified Relations"][0]["Opportunity ID"] = "Opp-2"
        report = evaluate(data)
        self.assertEqual(report["sink"]["report_to_generated_readback_status"], "SINK_LAG")
        self.assertEqual(report["sink"]["relation_values_mismatch"], 1)

    def test_export_missing_opp_is_review_not_missing_object(self):
        data = fixture()
        data["SFDC Email Opportunities Raw"] = [{"Opportunity ID": "Opp-1"}]
        data["SFDC Email Ingest Audit"][1]["Rows"] = "1"
        data["SFDC Email Ingest Audit"][1]["Unique IDs"] = "1"
        stage = audit_source(data["SFDC Email Ingest Audit"], data["SFDC Email Leads Raw"],
                            data["SFDC Email Opportunities Raw"], data["SFDC Email Quotation Raw"])
        v, review, reasons = expected_relation(data["SFDC Email Quotation Raw"],
                                                data["SFDC Email Opportunities Raw"])
        self.assertNotIn("QID-4", v)
        self.assertIn("QID-4", review)
        self.assertIn("OPPORTUNITY_NOT_IN_EXPORT", review["QID-4"]["reason"])
        self.assertEqual(stage["opportunities"], 1)

    def test_report_audit_count_drift_blocks(self):
        data = fixture()
        data["SFDC Email Ingest Audit"][2]["Rows"] = "7"
        with self.assertRaisesRegex(ValueError, "COUNT_OR_ID_MISMATCH"):
            evaluate(data)

    def test_source_report_without_valid_provenance_blocks(self):
        data = fixture()
        data["SFDC Email Ingest Audit"][2]["State"] = "SOURCE_UNAVAILABLE"
        with self.assertRaisesRegex(ValueError, "STAGE_NOT_ACCEPTED"):
            evaluate(data)

    def test_duplicate_quote_id_in_generated_sink_blocks(self):
        data = fixture()
        data["SFDC Verified Relations"].append(copy.deepcopy(data["SFDC Verified Relations"][0]))
        with self.assertRaisesRegex(ValueError, "PRIMARY_ID_MISSING_OR_DUPLICATE"):
            evaluate(data)

    def test_unexpected_derived_quote_id_blocks(self):
        data = fixture()
        row = copy.deepcopy(data["SFDC Verified Relations"][0])
        row["Quotation ID"] = "QID-FAKE"
        data["SFDC Verified Relations"].append(row)
        result = evaluate(data)
        self.assertEqual(result["sink"]["sink_quote_ids_not_in_source"], 1)
        self.assertEqual(result["sink"]["report_to_generated_readback_status"], "SINK_LAG")

    def test_missing_immutable_source_id_blocks(self):
        data = fixture()
        data["SFDC Email Opportunities Raw"][0]["Opportunity ID"] = ""
        with self.assertRaisesRegex(ValueError, "PRIMARY_ID_MISSING_OR_DUPLICATE"):
            evaluate(data)

    def test_multiple_opportunity_ids_one_quote_is_not_valid(self):
        data = fixture()
        data["SFDC Email Quotation Raw"][1]["Opportunity ID"] = "Opp-2"
        verified, review, reasons = expected_relation(data["SFDC Email Quotation Raw"],
                                                      data["SFDC Email Opportunities Raw"])
        self.assertNotIn("QID-1", verified)
        self.assertEqual(review["QID-1"]["distinct"], 2)
        self.assertEqual(reasons["MULTIPLE_OR_ZERO_OPPORTUNITY_IDS"], 2)

    def test_empty_review_tab_header_is_permitted(self):
        rows = parse([["Quotation ID", "Quote Process Rows", "Distinct Opportunity IDs",
                "Opportunity ID Missing Rows", "Opportunity IDs Not In Export", "Reason",
                "Review State"]], "SFDC Quote Link Review")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
