"""No-network, no-Save regressions for Salesforce 006 -> Novogene Opp-ID evidence."""
import unittest

from verify_business_opportunity_id import verify
from attach_existing_opportunity_reference import identity_status
from existing_opportunity_snapshot import SNAPSHOT_JS

SF = "006123456789ABCDEF"
BUSINESS = "Opp-2026-10-23-291068"
OTHER = "Opp-2026-10-23-291069"


def snapshot(fields=None, candidates=None):
    return {
        "source": "Salesforce visible UI",
        "saved_or_modified": False,
        "record_id_evidence": "lightning_opportunity_route",
        "record_id_from_url": SF,
        "frames": [{"fields": fields or [], "business_id_candidates": candidates or []}],
    }


def catalog(*ids):
    return [{"opportunity_id": value} for value in ids]


def field(label, value):
    return {"label": label, "value": value}


class BusinessIdBridgeTests(unittest.TestCase):
    def test_direct_labeled_value_and_single_catalog_row(self):
        result = verify(snapshot([field("Opportunity ID", BUSINESS)]), catalog(BUSINESS))
        self.assertEqual(result["status"], "VERIFIED_BUSINESS_ID_MATCH")
        self.assertEqual(result["matched_catalog_business_ids"], [BUSINESS])
        self.assertFalse(result["save_allowed"])

    def test_record_id_is_not_business_id(self):
        result = verify(snapshot(), catalog(BUSINESS))
        self.assertEqual(result["status"], "BUSINESS_ID_NOT_FOUND_OR_NOT_UNIQUE")
        self.assertEqual(result["matched_catalog_business_ids"], [])

    def test_unrelated_opportunity_name_does_not_certify_id(self):
        result = verify(snapshot([field("Opportunity Name", BUSINESS)]), catalog(BUSINESS))
        self.assertEqual(result["status"], "BUSINESS_ID_NOT_FOUND_OR_NOT_UNIQUE")

    def test_nearby_dom_candidate_stays_review(self):
        result = verify(snapshot(candidates=[{"id": BUSINESS}]), catalog(BUSINESS))
        self.assertEqual(result["status"], "CANDIDATE_MATCH_NEEDS_REVIEW")
        self.assertEqual(result["matched_catalog_business_ids"], [])

    def test_wrong_catalog_member_blocks(self):
        result = verify(snapshot([field("Opportunity ID", BUSINESS)]), catalog(OTHER))
        self.assertEqual(result["status"], "BUSINESS_ID_NOT_IN_CATALOG")

    def test_duplicate_catalog_rows_are_not_verified(self):
        result = verify(snapshot([field("Opportunity ID", BUSINESS)]), catalog(BUSINESS, BUSINESS))
        self.assertEqual(result["status"], "DUPLICATE_CATALOG_BUSINESS_ID")

    def test_conflicting_ui_ids_block(self):
        result = verify(snapshot([field("Opportunity ID", BUSINESS),
                                 field("Opportunity ID", OTHER)]), catalog(BUSINESS, OTHER))
        self.assertEqual(result["status"], "CONFLICTING_BUSINESS_IDS")
        self.assertEqual(result["matched_catalog_business_ids"], [])

    def test_user_confirmation_requires_exact_id(self):
        result = verify(snapshot(), catalog(BUSINESS), observed_business_id=BUSINESS)
        self.assertEqual(result["status"], "VERIFIED_BY_USER_SYSTEM_INFORMATION")
        with self.assertRaises(ValueError):
            verify(snapshot(), catalog(BUSINESS), observed_business_id="Opp-not-an-id")

    def test_user_confirmed_id_conflicting_with_ui_blocks(self):
        result = verify(snapshot([field("Opportunity ID", OTHER)]),
                        catalog(BUSINESS, OTHER), observed_business_id=BUSINESS)
        self.assertEqual(result["status"], "CONFLICTING_BUSINESS_IDS")

    def test_snapshot_needs_authentic_readonly_006_route(self):
        for key, value in [("source", "Spreadsheet"), ("saved_or_modified", True),
                           ("record_id_evidence", "guess"), ("record_id_from_url", BUSINESS)]:
            sample = snapshot()
            sample[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(sample, catalog(BUSINESS))

    def test_snapshot_js_regex_handles_business_id(self):
        # Source is Python raw string holding JS regex literal.
        self.assertIn(r"Opp-\d{4}-\d{2}-\d{2}-\d+", SNAPSHOT_JS)
        self.assertNotIn(r"Opp-\\d{4}", SNAPSHOT_JS)


class AttachIdentityTests(unittest.TestCase):
    def setUp(self):
        self.draft = {"source_opportunity_id": BUSINESS, "save_allowed": False}
        self.snap = snapshot([field("Opportunity ID", BUSINESS)])
        self.bridge = verify(self.snap, catalog(BUSINESS))

    def test_without_bridge_cannot_verify(self):
        self.assertEqual(identity_status(self.draft, self.snap), "BUSINESS_ID_BRIDGE_REQUIRED")

    def test_valid_bridge_maps_two_separate_id_namespaces(self):
        self.assertEqual(identity_status(self.draft, self.snap, self.bridge),
                         "VERIFIED_BUSINESS_ID_BRIDGE")

    def test_mismatched_salesforce_record_is_blocked(self):
        self.bridge["web_record_id"] = "006111111111111AAA"
        self.assertEqual(identity_status(self.draft, self.snap, self.bridge),
                         "BRIDGE_RECORD_MISMATCH")

    def test_mismatched_business_record_is_blocked(self):
        self.draft["source_opportunity_id"] = OTHER
        self.assertEqual(identity_status(self.draft, self.snap, self.bridge),
                         "BRIDGE_BUSINESS_ID_MISMATCH")

    def test_nearby_candidate_bridge_cannot_be_used(self):
        weak = verify(snapshot(candidates=[{"id": BUSINESS}]), catalog(BUSINESS))
        self.assertEqual(identity_status(self.draft, self.snap, weak), "BRIDGE_NOT_VERIFIED")

    def test_bad_route_cannot_be_reused(self):
        self.snap["record_id_evidence"] = "NOT_FOUND"
        self.assertEqual(identity_status(self.draft, self.snap, self.bridge), "INVALID_SFDC_ROUTE")


if __name__ == "__main__":
    unittest.main()
