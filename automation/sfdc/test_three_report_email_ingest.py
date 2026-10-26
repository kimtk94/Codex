#!/usr/bin/env python3
"""Offline contract tests for three Salesforce subscription report imports."""
import io
import sys
import pathlib
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from three_report_email_ingest import matrix, classify, validate, digest, filter_fresh
from three_report_relationship_qc import compare

class ReportIngestTests(unittest.TestCase):
    def fixture(self, kind, count):
        if kind == "Leads":
            headers = ["SFDC Lead ID", "Lead ID", "Opportunity ID.1", "Description"]
            rows = [[f"00Q{i:05d}", f"Lead-{i}", "", f"Inquiry {i}"] for i in range(count)]
        elif kind == "Opportunities":
            headers = ["Opportunity ID", "Lead Converted ID", "Stage"]
            rows = [[f"Opp-{i}", f"Lead-{i}", "Prospective"] for i in range(count)]
        else:
            headers = ["SFDC Quotation ID", "Quotation Product ID", "Opportunity ID", "Quote Process Name"]
            rows = [[f"QID-{i//3}", f"QD-{i//2}", f"Opp-{i//3}", "Sequencing"] for i in range(count)]
        text = "<table><tr>" + "".join("<th>" + h + "</th>" for h in headers) + "</tr>"
        text += "".join("<tr>" + "".join("<td>" + v + "</td>" for v in row) + "</tr>" for row in rows) + "</table>"
        return text.encode("utf-8"), headers, rows

    def test_all_three_schemas(self):
        for kind, count in (("Leads", 60), ("Opportunities", 110), ("Quotation", 120)):
            with self.subTest(kind=kind):
                blob, headers, rows = self.fixture(kind, count)
                found_headers, found_rows = matrix(blob, "sf.xls")
                self.assertEqual(classify(found_headers), kind)
                stats = validate(kind, found_headers, found_rows)
                self.assertEqual(stats["rows"], count)
                self.assertEqual(stats["missing"], 0)
                self.assertEqual(digest(found_headers, found_rows), digest(headers, rows))
    def test_conflicting_lead_ids_rejected(self):
        _, headers, rows = self.fixture("Leads", 60)
        rows[-1][0] = rows[0][0]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PRIMARY_IDS"):
            validate("Leads", headers, rows)
    def test_missing_opportunity_id_rejected(self):
        _, headers, rows = self.fixture("Opportunities", 110)
        rows[0][0] = ""
        with self.assertRaisesRegex(ValueError, "MISSING_REQUIRED_IDS"):
            validate("Opportunities", headers, rows)
    def test_truncated_export_rejected(self):
        _, headers, rows = self.fixture("Quotation", 120)
        with self.assertRaisesRegex(ValueError, "TOO_FEW_ROWS"):
            validate("Quotation", headers, rows[:4])
    def test_quote_process_duplicates_allowed(self):
        _, headers, rows = self.fixture("Quotation", 120)
        stats = validate("Quotation", headers, rows)
        self.assertLess(stats["unique"], stats["rows"])
        self.assertGreater(stats["duplicates"], 0)
    def test_freshness_prevents_rollback(self):
        prior={"Leads":["Leads","2026-10-26 12:00:00 KST","","","","","","hash1","",""]}
        older={"Leads":{"stamp":"2026-10-26 08:00:00 KST","sha":"hash0"}}
        self.assertEqual(filter_fresh(older,prior),{})
        same={"Leads":{"stamp":"2026-10-26 12:00:00 KST","sha":"hash1"}}
        self.assertEqual(filter_fresh(same,prior),{})
        newer={"Leads":{"stamp":"2026-10-26 17:00:00 KST","sha":"hash2"}}
        self.assertEqual(filter_fresh(newer,prior),newer)

    def test_relation_audit_counts_process_rows_and_unique_quotes(self):
        leads=[["Lead ID"],["Lead-1"]]
        opportunities=[["Opportunity ID","Lead Converted ID"],["Opp-1","Lead-1"]]
        quotes=[["SFDC Quotation ID","Opportunity ID"],["Q-1","Opp-1"],["Q-1","Opp-1"],["Q-2","Opp-missing"],["Q-3",""]]
        result=compare(leads, opportunities, quotes)
        self.assertEqual(result["quotation_process_rows"],4)
        self.assertEqual(result["unique_quote_ids"],3)
        self.assertEqual(result["linked_quote_rows"],2)
        self.assertEqual(result["unique_quote_ids_with_link_issue"],2)
        self.assertEqual(result["qc"],"REVIEW")

    def test_unknown_attachment_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNRECOGNIZED_REPORT_SCHEMA"):
            matrix(b"<table><tr><th>Other</th><th>Amount</th></tr><tr><td>A</td><td>100</td></tr></table>", "x.xls")

if __name__ == "__main__":
    unittest.main()
