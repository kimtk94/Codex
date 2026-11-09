"""Independent historical SF record evidence is not a live SFDC object audit."""
import copy
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from three_report_owner_historical_quote_evidence import (
    historic_export_audit, compare_owner_priority,
)

UTC = dt.timezone.utc
CHECKED = dt.datetime(2026, 11, 9, 0, 30, tzinfo=UTC)


def example():
    opp = [
        {"Opportunity ID": "Opp-1", "Opportunity Owner": "Kim Taehoon",
         "Stage": "Quotation Issued"},
        {"Opportunity ID": "Opp-2", "Opportunity Owner": "Kim Taehoon",
         "Stage": "Proposal Sent"},
        {"Opportunity ID": "Opp-3", "Opportunity Owner": "Kim Taehoon",
         "Stage": "Closed Won"},
        {"Opportunity ID": "Opp-4", "Opportunity Owner": "Other Seller",
         "Stage": "Quotation Issued"},
    ]
    new = [{
        "SFDC Quotation ID": "QID-new", "Opportunity ID": "Opp-4",
    }]
    past = [{
        "AMEA Quotation ID": "QID-old",
        "Salesforce Record ID": "a0PTK00000uDfbP2AS",
        "Opportunity ID": "Opp-1",
        "IsActive": "1",
        "Exported At KST": "2026-10-24 18:00:08 KST",
    }, {
        "AMEA Quotation ID": "QID-new",
        "Salesforce Record ID": "a0PTK00000BR2FV2A1",
        "Opportunity ID": "Opp-4",
        "IsActive": "0",
        "Exported At KST": "2026-10-24 18:00:08 KST",
    }]
    return opp, new, past


class HistoricalQuoteTests(unittest.TestCase):
    def test_owner_priorities_classified_without_current_object_claim(self):
        opp, new, past = example()
        got = compare_owner_priority(opp, new, past, checked_at=CHECKED)
        self.assertEqual(got["owner_without_staged_quote_opportunities"], 3)
        self.assertEqual(got["priority_opportunity_count"], 3)
        self.assertEqual(got["priority_with_historic_record_id"], 1)
        self.assertEqual(got["priority_without_historic_record_id"], 2)
        self.assertEqual(got["priority_historic_matches_by_stage"], {"Quotation Issued": 1})
        self.assertEqual(got["historical_quote_ids_absent_in_current_export_for_priority"], 1)
        self.assertEqual(got["historical_export_quote_ids_also_in_latest_staging"], 1)
        self.assertEqual(got["historical_export_quote_ids_absent_from_latest_staging"], 1)
        self.assertEqual(got["review_status"], "PASS_HISTORICAL_CORROBORATION_ONLY")
        self.assertFalse(got["latest_sf_quote_exists_certified"])
        self.assertFalse(got["historic_export_is_live_sfdc_api"])
        self.assertEqual(got["owner_priority_live_sf_objects_verified"], 0)

    def test_no_old_record_means_unknown_not_object_absent(self):
        opp, new, past = example()
        got = compare_owner_priority(opp, new, past[1:], checked_at=CHECKED)
        self.assertEqual(got["priority_with_historic_record_id"], 0)
        self.assertEqual(got["priority_without_historic_record_id"], 3)
        self.assertTrue(got["candidate_without_old_evidence_is_not_proof_of_absence"])

    def test_no_owner_inference_from_name_or_account(self):
        opp, new, past = example()
        opp[3]["Account Name"] = "Kim Taehoon"
        opp[3]["Contact Name"] = "Kim Taehoon"
        got = compare_owner_priority(opp, new, past, checked_at=CHECKED)
        self.assertEqual(got["owner_without_staged_quote_opportunities"], 3)

    def test_quote_id_in_current_export_with_different_opportunity_blocks(self):
        opp, new, past = example()
        new.append({"SFDC Quotation ID": "QID-old", "Opportunity ID": "Opp-4"})
        got = compare_owner_priority(opp, new, past, checked_at=CHECKED)
        self.assertEqual(got["review_status"], "BLOCK_CONFLICTING_STAGED_QID_RELATION")
        self.assertEqual(got["historic_quote_opportunity_conflict_count"], 1)

    def test_old_quote_missing_opp_id_is_explicit_unattributable_exception(self):
        opp, new, past = example()
        unassigned = dict(past[1])
        unassigned["Salesforce Record ID"] = "a0PTK00000BR2FV2B2"
        unassigned["AMEA Quotation ID"] = "QID-no-opp"
        unassigned["Opportunity ID"] = ""
        result = compare_owner_priority(opp, new, past + [unassigned], checked_at=CHECKED)
        self.assertEqual(result["historical_export_unattributable_no_opp_id"], 1)
        self.assertEqual(result["priority_with_historic_record_id"], 1)
        self.assertEqual(result["review_status"],
                         "REVIEW_HISTORICAL_EXPORT_OPPORTUNITY_ID_GAP")
        self.assertFalse(result["latest_sf_quote_exists_certified"])

    def test_duplicate_historic_quote_ids_fail_closed(self):
        _, _, past = example()
        dup = copy.deepcopy(past[0])
        dup["Salesforce Record ID"] = "a0PTK00000BR2FV2A1"
        with self.assertRaisesRegex(ValueError, "HISTORIC_QUOTE_DUPLICATE_ID"):
            historic_export_audit([past[0], dup], checked_at=CHECKED)

    def test_duplicate_sf_record_ids_fail_closed(self):
        _, _, past = example()
        past[1]["Salesforce Record ID"] = past[0]["Salesforce Record ID"]
        with self.assertRaisesRegex(ValueError, "HISTORIC_QUOTE_DUPLICATE_ID"):
            historic_export_audit(past, checked_at=CHECKED)

    def test_invalid_sf_record_id_cannot_certify_history(self):
        _, _, past = example()
        past[0]["Salesforce Record ID"] = "12345"
        with self.assertRaisesRegex(ValueError, "HISTORIC_SF_RECORD_ID_MALFORMED"):
            historic_export_audit(past, checked_at=CHECKED)

    def test_future_historical_export_is_not_evidence(self):
        _, _, past = example()
        past[0]["Exported At KST"] = "2026-11-20 00:00:00 KST"
        with self.assertRaisesRegex(ValueError, "HISTORIC_QUOTE_FUTURE_TIMESTAMP"):
            historic_export_audit(past, checked_at=CHECKED)

    def test_missing_export_timestamp_blocks(self):
        _, _, past = example()
        past[0]["Exported At KST"] = ""
        with self.assertRaisesRegex(ValueError, "HISTORIC_QUOTE_ID_OR_PROVENANCE_MISSING"):
            historic_export_audit(past, checked_at=CHECKED)

    def test_opportunity_id_duplicate_blocks(self):
        opp, new, past = example()
        opp.append(copy.deepcopy(opp[0]))
        with self.assertRaisesRegex(ValueError, "OPPORTUNITY_ID_MISSING_OR_DUPLICATE"):
            compare_owner_priority(opp, new, past, checked_at=CHECKED)

    def test_current_quote_appearing_on_original_opp_is_excluded_from_priority(self):
        opp, new, past = example()
        new.append({"SFDC Quotation ID": "QID-old", "Opportunity ID": "Opp-1"})
        got = compare_owner_priority(opp, new, past, checked_at=CHECKED)
        self.assertEqual(got["priority_opportunity_count"], 2)
        self.assertEqual(got["priority_with_historic_record_id"], 0)
        self.assertEqual(got["review_status"], "PASS_HISTORICAL_CORROBORATION_ONLY")

    def test_no_sf_record_data_never_yields_empty_pass(self):
        opp, new, _ = example()
        with self.assertRaisesRegex(ValueError, "HISTORICAL_SFDC_QUOTE_EXPORT_MISSING"):
            compare_owner_priority(opp, new, [], checked_at=CHECKED)


if __name__ == "__main__":
    unittest.main()
