"""Synthetic offline regressions for direct Salesforce Report -> Opportunity link."""
import unittest

from live_quotation_report_bridge import verify

SF = "006000000000000AAA"
QUOTE = "a0P000000000000AAA"
QID = "QID-2099-01-01-111111"
OPP = "Opp-2099-01-01-222222"
OTHER = "Opp-2099-01-01-222223"


def related():
    return {"source": "Salesforce Opportunity Related + Quotation visible UI",
            "salesforce_modified": False, "opportunity_record_id": SF,
            "related_quote_record_id": QUOTE, "quotation_record_id": QUOTE,
            "related_qid": QID}


def report():
    return {"source": "Salesforce Report Viewer UI", "salesforce_modified": False,
            "report_id": "00O000000000000AAA", "exact_qid_filter": QID,
            "filter_operator": "equals", "total_records": 4,
            "rows": [{"qid": QID, "quotation_record_id": QUOTE,
                      "business_opportunity_id": OPP} for _ in range(4)]}


class LiveReportBridgeTests(unittest.TestCase):
    def test_four_products_one_quote_business_opportunity(self):
        result = verify(related(), report())
        self.assertEqual(result["status"], "VERIFIED_BY_LIVE_QUOTATION_REPORT")
        self.assertEqual(result["verified_product_rows"], 4)
        self.assertEqual(result["business_opportunity_id"], OPP)
        self.assertFalse(result["save_allowed"])
        self.assertTrue(result["review_required"])

    def test_missing_report_record_is_hold(self):
        data = report()
        data["total_records"] = 0
        data["rows"] = []
        self.assertEqual(verify(related(), data)["status"],
                         "REPORT_ROWS_INCOMPLETE_OR_EMPTY")

    def test_2000_display_limit_cannot_certify_truncated_report(self):
        data = report()
        data["total_records"] = 2001
        self.assertEqual(verify(related(), data)["status"],
                         "REPORT_ROWS_INCOMPLETE_OR_EMPTY")

    def test_total_count_mismatch_is_hold(self):
        data = report()
        data["total_records"] = 5
        self.assertEqual(verify(related(), data)["status"],
                         "REPORT_ROWS_INCOMPLETE_OR_EMPTY")

    def test_row_quote_record_mismatch_is_hold(self):
        data = report()
        data["rows"][2]["quotation_record_id"] = "a0P000000000001AAA"
        self.assertEqual(verify(related(), data)["status"],
                         "REPORT_ROW_QUOTE_ID_CONFLICT")

    def test_row_qid_mismatch_is_hold(self):
        data = report()
        data["rows"][0]["qid"] = "QID-2099-01-01-111112"
        self.assertEqual(verify(related(), data)["status"],
                         "REPORT_ROW_QUOTE_ID_CONFLICT")

    def test_business_id_conflict_is_hold(self):
        data = report()
        data["rows"][3]["business_opportunity_id"] = OTHER
        self.assertEqual(verify(related(), data)["status"],
                         "CONFLICTING_BUSINESS_IDS")

    def test_invalid_business_id_is_hold(self):
        data = report()
        data["rows"][0]["business_opportunity_id"] = SF
        self.assertEqual(verify(related(), data)["status"],
                         "REPORT_ROW_BUSINESS_ID_INVALID")

    def test_report_without_exact_filter_not_authorized(self):
        data = report()
        data["filter_operator"] = "contains"
        with self.assertRaises(ValueError):
            verify(related(), data)

    def test_unverified_related_link_rejected(self):
        e = related()
        e["related_quote_record_id"] = "a0P000000000001AAA"
        with self.assertRaises(ValueError):
            verify(e, report())

    def test_fake_report_origin_rejected(self):
        data = report()
        data["source"] = "Google Sheets"
        with self.assertRaises(ValueError):
            verify(related(), data)

    def test_saving_flag_blocks(self):
        data = report()
        data["salesforce_modified"] = True
        with self.assertRaises(ValueError):
            verify(related(), data)


if __name__ == "__main__":
    unittest.main()
