"""No-network safety checks for Opportunity Related Quotation / Quote Export bridge."""
import unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta

from related_quotation_bridge import bridge, same_record

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
QID = "QID-2026-11-02-410997"
SF = "006TK00000u7ljVYAQ"
QUOTE = "a0PTK000010t6fO2AQ"
OPP = "Opp-2026-11-02-440997"


def evidence():
    return {"source": "Salesforce Opportunity Related + Quotation visible UI",
            "salesforce_modified": False, "opportunity_record_id": SF,
            "related_quote_record_id": QUOTE,
            "quotation_record_id": QUOTE, "related_qid": QID}


def row(**updates):
    src = {"Salesforce Record ID": QUOTE, "AMEA Quotation ID": QID,
           "Opportunity ID": OPP, "Exported At KST": "2026-11-02 18:00:00 KST"}
    src.update(updates)
    return src


class BridgeTests(unittest.TestCase):
    def check(self, source, artifact=None):
        return bridge(artifact or evidence(), source, at_time=NOW)

    def test_authoritative_record_and_qid_both_exact(self):
        result = self.check([row()])
        self.assertEqual(result["status"], "SOURCE_BACKED_RELATED_QUOTE_MATCH")
        self.assertEqual(result["opportunity_business_id"], OPP)
        self.assertTrue(result["reference_reuse_allowed"])
        self.assertFalse(result["save_allowed"])

    def test_no_source_row_is_hold(self):
        r = self.check([])
        self.assertEqual(r["status"], "QUOTE_NOT_IN_SOURCE")
        self.assertIsNone(r["opportunity_business_id"])

    def test_weak_name_only_cannot_join(self):
        r = self.check([{"Quotation Name": "same name",
                         "Opportunity ID": OPP, "Exported At KST": "2026-11-02 18:00:00 KST"}])
        self.assertEqual(r["status"], "QUOTE_NOT_IN_SOURCE")

    def test_qid_matching_wrong_quote_record_is_conflict(self):
        r = self.check([row(**{"Salesforce Record ID": "a0PTK000010t6fP2AQ"})])
        self.assertEqual(r["status"], "QUOTE_RECORD_QID_CONFLICT")

    def test_quote_record_matching_wrong_qid_is_conflict(self):
        r = self.check([row(**{"AMEA Quotation ID": "QID-2026-11-02-410998"})])
        self.assertEqual(r["status"], "QUOTE_RECORD_QID_CONFLICT")

    def test_duplicate_rows_fail_closed(self):
        r = self.check([row(), row()])
        self.assertEqual(r["status"], "AMBIGUOUS_SOURCE_RECORD")

    def test_conflicting_rows_fail_closed(self):
        r = self.check([row(), row(**{"AMEA Quotation ID": "QID-2026-11-02-410998"})])
        self.assertEqual(r["status"], "AMBIGUOUS_SOURCE_RECORD")

    def test_source_must_contain_valid_business_id(self):
        r = self.check([row(**{"Opportunity ID": "006TK00000u7ljVYAQ"})])
        self.assertEqual(r["status"], "BUSINESS_ID_MISSING_OR_INVALID")

    def test_stale_source_does_not_certify(self):
        r = self.check([row(**{"Exported At KST": "2026-10-24 18:00:00 KST"})])
        self.assertEqual(r["status"], "SOURCE_EXPORT_STALE_OR_UNVERIFIED")

    def test_future_or_missing_source_timestamp_not_certified(self):
        for value in ("", "2026-11-05 12:00:00 KST", "2026-11-02T18:00:00Z"):
            with self.subTest(value=value):
                r = self.check([row(**{"Exported At KST": value})])
                self.assertEqual(r["status"], "SOURCE_EXPORT_STALE_OR_UNVERIFIED")

    def test_quote_route_mismatch_rejected(self):
        ev = evidence()
        ev["quotation_record_id"] = "a0PTK000010t6fP2AQ"
        with self.assertRaises(ValueError):
            self.check([row()], ev)

    def test_wrong_parent_record_object_rejected(self):
        ev = evidence()
        ev["opportunity_record_id"] = QUOTE
        with self.assertRaises(ValueError):
            self.check([row()], ev)

    def test_fake_evidence_origin_rejected(self):
        ev = evidence()
        ev["source"] = "Spreadsheet"
        with self.assertRaises(ValueError):
            self.check([row()], ev)

    def test_missing_safety_evidence_rejected(self):
        ev = evidence()
        ev["salesforce_modified"] = None
        with self.assertRaises(ValueError):
            self.check([row()], ev)

    def test_first15_case_sensitive(self):
        self.assertTrue(same_record(SF, SF[:15]))
        self.assertFalse(same_record(SF, SF[:15].lower()))
        self.assertFalse(same_record(SF, ""))


if __name__ == "__main__":
    unittest.main()
