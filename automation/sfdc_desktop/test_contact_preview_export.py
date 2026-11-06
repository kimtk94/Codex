"""Synthetic-only verified Contact/Opportunity preview tests. No Salesforce network."""
import unittest
from contact_preview_export import (
    Hold, record_id, strict_single_view, verified_private_evidence,
)

QUERY = "김민수"
OPP = "006000000000AAA"
CANDIDATE = {
    "contact_id": "003000000000AAA",
    "account_id": "001000000000AAA",
    "korean_name": QUERY,
    "institution_name": "합성대학교 산학협력단",
    "email": "synthetic@example.org",
    "opportunity_contact_id": "003000000000AAA",
    "opportunity_account_id": "001000000000AAA",
}

class PreviewExportContractTests(unittest.TestCase):
    def good(self, **changes):
        return verified_private_evidence(
            QUERY, {**CANDIDATE, **changes}, OPP,
            timestamp="2026-11-06T01:00:00+00:00")

    def test_record_id_from_custom_or_standard_lightning_url(self):
        self.assertEqual(record_id("https://example.org/lightning/r/Contact/003000000000AAA/view","003"),"003000000000AAA")
        self.assertEqual(record_id("https://example.org/lightning/r/003000000000AAA/view","003"),"003000000000AAA")

    def test_valid_single_all_contacts_query(self):
        self.assertEqual(strict_single_view(QUERY,"All Contacts","1 item - Updated\n1 item",[
            {"contact_id":"003000000000AAA","display_name":"김민수 Kim Minsu"}]),"003000000000AAA")

    def test_recently_viewed_is_not_full_query(self):
        with self.assertRaises(Hold):
            strict_single_view(QUERY,"Recently Viewed","1 item",
                 [{"contact_id":"003000000000AAA","display_name":QUERY}])

    def test_multiple_or_unverifiable_results_hold(self):
        for markers in ("2 items","50+ items","", "1 item\n2 items"):
            with self.subTest(markers=markers), self.assertRaises(Hold):
                strict_single_view(QUERY,"All Contacts",markers,
                  [{"contact_id":"003000000000AAA","display_name":QUERY}])

    def test_list_display_name_must_be_exact_korean(self):
        with self.assertRaises(Hold):
            strict_single_view(QUERY,"All Contacts","1 item",
                 [{"contact_id":"003000000000AAA","display_name":"김민수진 Kim"}])

    def test_valid_verified_no_save_evidence(self):
        payload=self.good()
        self.assertEqual(payload["query"],QUERY)
        self.assertEqual(payload["candidates"][0]["contact_id"],CANDIDATE["contact_id"])
        self.assertEqual(payload["candidates"][0]["linked_opportunity_ids"],[OPP])
        self.assertEqual(payload["unresolved_matches"],0)
        self.assertFalse(payload["salesforce_write_performed"])

    def test_wrong_main_contact_id_blocks(self):
        with self.assertRaises(Hold):
            self.good(opportunity_contact_id="003000000000AAB")

    def test_wrong_account_id_blocks(self):
        with self.assertRaises(Hold):
            self.good(opportunity_account_id="001000000000AAB")

    def test_missing_contact_email_blocks(self):
        with self.assertRaises(Hold):
            self.good(email="")

    def test_missing_account_label_blocks(self):
        with self.assertRaises(Hold):
            self.good(institution_name="")

    def test_excluded_accounts_block(self):
        for name in ("KAIST","한남대학교 산학협력단"):
            with self.subTest(name=name), self.assertRaises(Hold):
                self.good(institution_name=name)

    def test_opportunity_id_must_be_valid(self):
        with self.assertRaises(Hold):
            verified_private_evidence(QUERY,CANDIDATE,"NOT_SFID",timestamp="2026-11-06T00:00:00Z")

if __name__=="__main__":
    unittest.main()
