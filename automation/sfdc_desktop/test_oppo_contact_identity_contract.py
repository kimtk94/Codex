"""Synthetic tests only. No Salesforce session, credentials or writes."""
import unittest

from oppo_contact_identity_contract import OppoContactHold, eligible_contact


class OppoContactIdentityTests(unittest.TestCase):
    def setUp(self):
        self.oppo = {
            "opportunity_id": "006000000000AAA",
            "main_contact_id": "003000000000AAA",
            "account_id": "001000000000AAA",
        }
        self.contact = {
            "contact_id": "003000000000AAA",
            "account_id": "001000000000AAA",
            "korean_name": "김민수",
            "institution_name": "경북대학교 산학협력단",
            "email": "demo@example.org",
        }

    def verify_rejected(self, oppo=None, contact=None):
        with self.assertRaises(OppoContactHold):
            eligible_contact(oppo or self.oppo, contact or self.contact)

    def test_verified_source_ids_pass(self):
        v = eligible_contact(self.oppo, self.contact)
        self.assertEqual(v["contact_id"], self.oppo["main_contact_id"])
        self.assertEqual(v["account_id"], self.oppo["account_id"])
        self.assertEqual(v["linked_opportunity_ids"], [self.oppo["opportunity_id"]])
        self.assertFalse(v["save_clicked"])

    def test_name_alone_is_never_enough(self):
        self.verify_rejected({**self.oppo, "main_contact_id": "003000000000AAB"})

    def test_cross_institution_record_is_blocked(self):
        self.verify_rejected(contact={**self.contact, "account_id": "001000000000AAB"})

    def test_missing_main_contact_id_blocks(self):
        self.verify_rejected({**self.oppo, "main_contact_id": ""})

    def test_missing_opportunity_account_id_blocks(self):
        self.verify_rejected({**self.oppo, "account_id": ""})

    def test_invalid_contact_id_blocks(self):
        self.verify_rejected(contact={**self.contact, "contact_id": "FAKE"})

    def test_invalid_opportunity_id_blocks(self):
        self.verify_rejected({**self.oppo, "opportunity_id": "003000000000AAA"})

    def test_invalid_korean_name_blocks(self):
        self.verify_rejected(contact={**self.contact, "korean_name": "John Kim"})

    def test_blank_contact_email_blocks(self):
        self.verify_rejected(contact={**self.contact, "email": ""})

    def test_blank_institution_blocks(self):
        self.verify_rejected(contact={**self.contact, "institution_name": ""})

    def test_kaist_is_not_learning_eligible(self):
        self.verify_rejected(contact={**self.contact, "institution_name": "KAIST"})

    def test_hannam_is_not_learning_eligible(self):
        self.verify_rejected(contact={**self.contact, "institution_name": "한남대학교 산학협력단"})

    def test_web_index_has_no_save_permission(self):
        v = eligible_contact(self.oppo, self.contact)
        self.assertEqual(v["status"], "VERIFIED_SOURCE_LINKS_RECHECK_REQUIRED")
        self.assertNotIn("allow_save", v)
        self.assertNotIn("write", v)


if __name__ == "__main__":
    unittest.main()
