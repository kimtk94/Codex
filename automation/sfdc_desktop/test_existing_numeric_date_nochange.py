"""Synthetic safety regressions for no-change Amount/Close Date fill audit."""
import unittest

from audit_existing_numeric_date_nochange import (
    normalize_field_label, check_lookup_ids, NOOP_FIELDS, FIELD_LABEL
)

SF = "006000000000000AAA"
ACCOUNT = "001000000000000AAA"
CONTACT = "003000000000000AAA"


def known_links():
    return {
        "opportunity_record_id": SF,
        "account_contact_field_links_verified": True,
        "salesforce_save_performed": False,
        "account_record_id": ACCOUNT,
        "contact_record_id": CONTACT
    }


def displayed_links():
    return [
        {"object": "Account", "record_id": ACCOUNT,
         "is_account_name": True, "is_main_contact": False,
         "is_end_user_account": False, "is_end_user_contact": False},
        {"object": "Contact", "record_id": CONTACT,
         "is_account_name": False, "is_main_contact": True,
         "is_end_user_account": False, "is_end_user_contact": False},
    ]


class StrictFieldLabels(unittest.TestCase):
    def test_required_numeric_label(self):
        self.assertEqual(normalize_field_label("*Amount"), "Amount")

    def test_amount_plain_label(self):
        self.assertEqual(normalize_field_label("Amount"), "Amount")

    def test_close_date_required(self):
        self.assertEqual(normalize_field_label(" * Close Date "), "Close Date")

    def test_no_fuzzy_amount_names(self):
        for raw in ("Expected Revenue Amount", "Client Budget Amount",
                    "Expected Payment Amount", "Amount (converted)",
                    "Not Amount", ""):
            with self.subTest(label=raw):
                self.assertIsNone(normalize_field_label(raw))

    def test_no_unsupported_fields(self):
        self.assertEqual(set(NOOP_FIELDS), {"Amount", "Close Date"})
        self.assertIsNone(normalize_field_label("Stage"))
        self.assertIsNone(normalize_field_label("Account Name"))


class PrivateLookupEvidence(unittest.TestCase):
    def test_live_lookup_ids_identical(self):
        self.assertTrue(check_lookup_ids(known_links(), displayed_links(), SF))

    def test_wrong_opportunity_blocks_all(self):
        with self.assertRaises(ValueError):
            check_lookup_ids(known_links(), displayed_links(), "006000000000001AAA")

    def test_known_account_changed_blocks(self):
        local = known_links()
        local["account_record_id"] = "001000000000001AAA"
        with self.assertRaises(ValueError):
            check_lookup_ids(local, displayed_links(), SF)

    def test_known_contact_changed_blocks(self):
        local = known_links()
        local["contact_record_id"] = "003000000000001AAA"
        with self.assertRaises(ValueError):
            check_lookup_ids(local, displayed_links(), SF)

    def test_missing_verified_flag_blocks(self):
        local = known_links()
        local["account_contact_field_links_verified"] = False
        with self.assertRaises(ValueError):
            check_lookup_ids(local, displayed_links(), SF)

    def test_previously_saved_flag_blocks(self):
        local = known_links()
        local["salesforce_save_performed"] = True
        with self.assertRaises(ValueError):
            check_lookup_ids(local, displayed_links(), SF)

    def test_ambiguous_live_account_link_blocks(self):
        rows = displayed_links()
        rows.append(dict(rows[0]))
        with self.assertRaises(ValueError):
            check_lookup_ids(known_links(), rows, SF)

    def test_no_contact_link_blocks(self):
        with self.assertRaises(ValueError):
            check_lookup_ids(known_links(), displayed_links()[:1], SF)


if __name__ == "__main__":
    unittest.main()
