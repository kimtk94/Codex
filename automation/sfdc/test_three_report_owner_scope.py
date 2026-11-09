"""Owner scope: only exact source Opportunity ID can attest Quote owner."""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from three_report_owner_scope import owner_report_audit
from test_three_report_staged_vs_generated_audit import fixture


def source():
    data = fixture()
    data["SFDC Email Opportunities Raw"][0].update({
        "Opportunity Owner": "Kim Taehoon", "Stage": "Negotiation",
    })
    data["SFDC Email Opportunities Raw"][1].update({
        "Opportunity Owner": "Yoo Juyeon", "Stage": "Closed Won",
    })
    for i, row in enumerate(data["SFDC Email Quotation Raw"]):
        row["Active"] = "1" if i < 4 else "0"
    data["SFDC Verified Relations"][0].update({
        "Opportunity Owner": "Kim Taehoon", "Opportunity Stage": "Negotiation",
        "Quote Active (report only)": "1",
    })
    data["SFDC Verified Relations"][1].update({
        "Opportunity Owner": "Yoo Juyeon", "Opportunity Stage": "Closed Won",
        "Quote Active (report only)": "0",
    })
    return data


class TestOwnerScope(unittest.TestCase):
    def test_owner_opportunities_and_unique_quotes_not_process_rows(self):
        r = owner_report_audit(source())
        self.assertEqual(r["owner_opportunities"], 1)
        self.assertEqual(r["other_opportunities"], 1)
        self.assertEqual(r["owner_verified_quote_ids"], 1)
        self.assertEqual(r["other_verified_quote_ids"], 1)
        self.assertEqual(r["owner_verified_quote_process_rows"], 2)
        self.assertEqual(r["owner_quote_report_active_counts"], {"1": 1})
        self.assertEqual(r["owner_quote_stage_counts"], {"Negotiation": 1})
        self.assertEqual(r["scope_status"], "PASS_REPORT_OWNER_TO_SINK_ONLY")
        self.assertEqual(r["salesforce_saved_object_state"], "NOT_CHECKED")

    def test_exception_quote_cannot_be_assigned_from_account_or_customer_name(self):
        data = source()
        data["SFDC Email Quotation Raw"][2]["Contact Name: Full Name"] = "Kim Taehoon"
        data["SFDC Email Quotation Raw"][3]["Opportunity Name: Opportunity Name"] = "Kim Taehoon"
        r = owner_report_audit(data)
        self.assertEqual(r["review_unattributable_quote_ids"], 2)
        self.assertEqual(r["owner_verified_quote_ids"], 1)
        self.assertEqual(r["review_quote_owner_assignment"],
                         "NOT_PERMITTED_WITHOUT_EXACT_OPPORTUNITY_OWNER")

    def test_nonmatching_other_owner_not_mislabeled_mine(self):
        data = source()
        data["SFDC Email Opportunities Raw"][1]["Opportunity Owner"] = "Kim Taehoon-History"
        data["SFDC Verified Relations"][1]["Opportunity Owner"] = "Kim Taehoon-History"
        r = owner_report_audit(data)
        self.assertEqual(r["owner_verified_quote_ids"], 1)
        self.assertEqual(r["other_verified_quote_ids"], 1)

    def test_verified_sink_owner_field_drift_blocks(self):
        data = source()
        data["SFDC Verified Relations"][0]["Opportunity Owner"] = "Rui Qiao"
        r = owner_report_audit(data)
        self.assertEqual(r["owner_field_readback_mismatches"], 1)
        self.assertEqual(r["scope_status"], "BLOCK_OWNER_SOURCE_OR_SINK_MISMATCH")

    def test_verified_sink_stage_field_drift_blocks(self):
        data = source()
        data["SFDC Verified Relations"][0]["Opportunity Stage"] = "Closed Won"
        r = owner_report_audit(data)
        self.assertEqual(r["stage_field_readback_mismatches"], 1)
        self.assertEqual(r["scope_status"], "BLOCK_OWNER_SOURCE_OR_SINK_MISMATCH")

    def test_verified_sink_active_flag_drift_blocks(self):
        data = source()
        data["SFDC Verified Relations"][1]["Quote Active (report only)"] = "1"
        r = owner_report_audit(data)
        self.assertEqual(r["active_field_readback_mismatches"], 1)
        self.assertEqual(r["scope_status"], "BLOCK_OWNER_SOURCE_OR_SINK_MISMATCH")

    def test_owner_missing_in_raw_blocks_attestation(self):
        data = source()
        data["SFDC Email Opportunities Raw"][1]["Opportunity Owner"] = ""
        data["SFDC Verified Relations"][1]["Opportunity Owner"] = ""
        r = owner_report_audit(data)
        self.assertEqual(r["owner_opportunities_missing_owner_field"], 1)
        self.assertEqual(r["scope_status"], "BLOCK_OWNER_SOURCE_OR_SINK_MISMATCH")

    def test_wrong_owner_name_cannot_pass_with_zero_owner(self):
        with self.assertRaisesRegex(ValueError, "OWNER_NAME_NOT_IN_SOURCE"):
            owner_report_audit(source(), owner="Someone Else")

    def test_duplicate_verified_quote_id_fails_closed(self):
        data = source()
        data["SFDC Verified Relations"].append(
            copy.deepcopy(data["SFDC Verified Relations"][0]))
        with self.assertRaisesRegex(ValueError, "PRIMARY_ID_MISSING_OR_DUPLICATE"):
            owner_report_audit(data)

    def test_sink_missing_review_id_is_not_a_valid_owner_scope(self):
        data = source()
        data["SFDC Quote Link Review"].pop()
        with self.assertRaisesRegex(ValueError, "OWNER_SCOPE_NOT_ALLOWED_UNTIL_LINK_PARITY"):
            owner_report_audit(data)

    def test_owner_without_a_verified_quote_is_tracked_separately(self):
        data = source()
        data["SFDC Email Opportunities Raw"].append({
            "Opportunity ID": "Opp-3", "Opportunity Owner": "Kim Taehoon",
            "Stage": "Negotiation",
        })
        r = owner_report_audit(data)
        self.assertEqual(r["owner_opportunities"], 2)
        self.assertEqual(r["owner_opportunities_without_verified_quotes"], 1)
        self.assertEqual(r["owner_distinct_opportunities_with_verified_quotes"], 1)

    def test_owner_name_matching_is_whitespace_case_normalized(self):
        data = source()
        data["SFDC Email Opportunities Raw"][0]["Opportunity Owner"] = "  KIM   TAEHOON  "
        r = owner_report_audit(data)
        self.assertEqual(r["scope_status"], "PASS_REPORT_OWNER_TO_SINK_ONLY")
        self.assertEqual(r["owner_verified_quote_ids"], 1)


if __name__ == "__main__":
    unittest.main()
