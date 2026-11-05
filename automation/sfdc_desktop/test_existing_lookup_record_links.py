"""Synthetic offline tests for Account/Contact links on an existing Opportunity."""
import unittest
from capture_existing_lookup_links import validate_links

ACCOUNT = "001000000000000AAA"
CONTACT = "003000000000000AAA"


def candidates():
    return [
        {"object": "Account", "record_id": ACCOUNT,
         "is_account_name": True, "is_main_contact": False,
         "is_end_user_account": False, "is_end_user_contact": False},
        {"object": "Contact", "record_id": CONTACT,
         "is_account_name": False, "is_main_contact": True,
         "is_end_user_account": False, "is_end_user_contact": False},
    ]


class ExistingLookupRecordTests(unittest.TestCase):
    def test_exact_primary_links_accepted(self):
        ids = validate_links(candidates())
        self.assertEqual(ids["account_record_id"], ACCOUNT)
        self.assertEqual(ids["contact_record_id"], CONTACT)

    def test_extra_global_account_link_does_not_confuse_primary(self):
        rows = candidates() + [{"object": "Account", "record_id": ACCOUNT,
                                 "is_account_name": False,
                                 "is_end_user_account": False}]
        self.assertEqual(validate_links(rows)["account_record_id"], ACCOUNT)

    def test_missing_account_link_rejected(self):
        with self.assertRaises(ValueError):
            validate_links(candidates()[1:])

    def test_missing_contact_link_rejected(self):
        with self.assertRaises(ValueError):
            validate_links(candidates()[:1])

    def test_duplicate_matching_account_links_rejected(self):
        r = candidates()
        with self.assertRaises(ValueError):
            validate_links(r + [dict(r[0])])

    def test_duplicate_matching_contact_links_rejected(self):
        r = candidates()
        with self.assertRaises(ValueError):
            validate_links(r + [dict(r[1])])

    def test_account_wrong_record_type_rejected(self):
        r = candidates()
        r[0]["record_id"] = CONTACT
        with self.assertRaises(ValueError):
            validate_links(r)

    def test_contact_wrong_record_type_rejected(self):
        r = candidates()
        r[1]["record_id"] = ACCOUNT
        with self.assertRaises(ValueError):
            validate_links(r)

    def test_missing_label_cannot_certify_link(self):
        r = candidates()
        r[0]["is_account_name"] = False
        with self.assertRaises(ValueError):
            validate_links(r)

    def test_end_user_reference_cannot_substitute_primary(self):
        r = candidates()
        r[0]["is_end_user_account"] = True
        with self.assertRaises(ValueError):
            validate_links(r)

    def test_malformed_id_rejected(self):
        r = candidates()
        r[1]["record_id"] = "003"
        with self.assertRaises(ValueError):
            validate_links(r)

    def test_arbitrary_source_rejected(self):
        with self.assertRaises(ValueError):
            validate_links(None)


if __name__ == "__main__":
    unittest.main()
