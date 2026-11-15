"""Synthetic-only, no SFDC/Google access required."""
from collections import Counter
import hashlib
import json
import unittest
from oppo_quote_popular_patterns import build_report, normalize_matrix, verify_mail_audit, EXPECTED_OPP, EXPECTED_QUOTE


class PatternLearningTests(unittest.TestCase):
    def setup_rows(self, n=12):
        opps, lines = [], []
        processes = ["Library preparation", "Sequencing by data amount", "Analysis by sample", "Data release"]
        for i in range(n):
            oid = f"Opp-2026-11-15-{200000+i}"
            qid = f"QID-2026-11-15-{300000+i}"
            aid = f"001{'A'*12}"
            opps.append({"Opportunity ID": oid, "Account ID": aid, "Opportunity Owner": "Test", "Stage": "Closed Won", "Opportunity Name": "synthetic"})
            for p in processes:
                lines.append({"SFDC Quotation ID": qid, "Quotation Product ID": f"QD-{i}", "Opportunity ID": oid,
                              "Active": "1", "Quotation Process Name": ",".join(processes), "Quote Process Name": p,
                              "*Account Id": aid, "Data Unit": "G raw data" if p == "Sequencing by data amount" else "",
                              "Data Size": "6"})
        return opps, lines

    def test_common_template_from_entire_dataset(self):
        opps, lines = self.setup_rows()
        output = build_report(opps, lines)
        self.assertEqual(output["source"]["unique_quotes"], 12)
        self.assertEqual(output["source"]["quote_process_rows"], 48)
        self.assertEqual(output["coverage"]["popular_template_quotes"], 12)
        self.assertEqual(output["coverage"]["eligible_quotes"], 12)
        self.assertEqual(output["policy"]["crm_writes"], 0)
        self.assertEqual(output["sequencing_gb_observed_median_not_default"], 6)
        self.assertNotIn("QID-", json.dumps(output))
        self.assertNotIn("Opp-", json.dumps(output))

    def test_exclude_inactive_multiline_conflict_and_multiproduct(self):
        opps, lines = self.setup_rows()
        for r in lines[:4]:
            r["Active"] = "0"
        for r in lines[4:8]:
            r["Quotation Product ID"] = "QD-B" if r["Quote Process Name"] == "Data release" else "QD-A"
        for r in lines[8:12]:
            r["Opportunity ID"] = "Opp-2026-11-15-999999"
        for r in lines[12:16]:
            r["Quote Process Name"] = "Wrong process"
        output = build_report(opps, lines)
        self.assertEqual(output["coverage"]["eligible_quotes"], 8)
        self.assertEqual(output["coverage"]["popular_template_quotes"], 0)
        reasons = output["coverage"]["exclude_reasons"]
        self.assertEqual(reasons["INACTIVE_OR_CONFLICTING_ACTIVE"], 1)
        self.assertEqual(reasons["MULTI_PRODUCT_MANUAL_REVIEW"], 1)
        self.assertEqual(reasons["OPPORTUNITY_OUTSIDE_REPORT_SCOPE"], 1)
        self.assertEqual(reasons["PROCESS_TEMPLATE_INCONSISTENT"], 1)

    def test_sha256_audit_rejects_tamper(self):
        opps, lines = self.setup_rows(1)
        def mat(rows, names):
            table = [names] + [[r.get(k, "") for k in names] for r in rows]
            return normalize_matrix(table, set(names))
        a = mat(opps, ["Opportunity ID", "Account ID", "Opportunity Owner", "Stage", "Opportunity Name"])
        b = mat(lines, ["SFDC Quotation ID", "Quotation Product ID", "Opportunity ID", "Active", "Quotation Process Name", "Quote Process Name", "*Account Id", "Data Unit", "Data Size"])
        matrices = {"opportunities": a, "quotation": b}
        audit = []
        for entity, key in [("Opportunities", "opportunities"), ("Quotation", "quotation")]:
            h, rr, rows = matrices[key]
            audit.append({"Entity": entity, "State": "PRESERVED_NO_NEW_REPORT", "Source Kind": "QQ IMAP",
                          "Rows": str(len(rows)), "Unique IDs": "1", "Missing IDs": "0",
                          "Content SHA256": hashlib.sha256(json.dumps([h, rr], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()})
        self.assertTrue(verify_mail_audit(matrices, audit)["quotation"]["hash_verified"])
        audit[1]["Content SHA256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
            verify_mail_audit(matrices, audit)


if __name__ == "__main__":
    unittest.main()