"""Synthetic Contact-first intake tests. No Salesforce connection or writes."""
import unittest
from sfdc_prepare_unsaved_opportunity import intake_contract,contact_origin_url

def valid():
    return {"name":"Korea-Synthetic-4-PMP-5Gb",
        "closeDate":"2026-12-18",
        "description":"1118 Quote Issued PMP 5Gb 4 samples * 57,500KRW",
        "contactId":"003000000000001",
        "accountId":"001000000000001"}

class ContactFirstIntakeTest(unittest.TestCase):
    def test_verified_contact_request_schema(self):
        self.assertIsNone(intake_contract(valid()))
    def test_missing_contact_or_account_holds(self):
        for key in ["contactId","accountId"]:
            payload=valid()
            del payload[key]
            self.assertEqual(intake_contract(payload),"CONTACT_ORIGIN_REQUEST_INVALID")
    def test_global_list_or_noncontact_url_rejected(self):
        self.assertFalse(contact_origin_url(
            "https://novogene.lightning.force.com/lightning/o/Opportunity/list",
            "003000000000001"))
        self.assertFalse(contact_origin_url(
            "https://novogene.lightning.force.com/lightning/r/Contact/003000000000002/view",
            "003000000000001"))
        self.assertTrue(contact_origin_url(
            "https://novogene.lightning.force.com/lightning/r/Contact/003000000000001/related",
            "003000000000001"))
    def test_draft_status_not_allowed_in_generated_progress(self):
        p=valid();p["description"]="1118 Quote Draft PMP 5Gb 4 samples * 57,500KRW"
        self.assertEqual(intake_contract(p),"QUOTE_ISSUED_DESCRIPTION_REQUIRED")
    def test_invalid_native_contact_id(self):
        p=valid();p["contactId"]="006000000000001"
        self.assertEqual(intake_contract(p),"EXISTING_CONTACT_NATIVE_ID_REQUIRED")
    def test_price_status_does_not_auto_create_salesforce(self):
        p=valid();self.assertIsNone(intake_contract(p))
        self.assertNotIn("save",p)
        self.assertNotIn("write",p)

if __name__=="__main__":
    unittest.main()
