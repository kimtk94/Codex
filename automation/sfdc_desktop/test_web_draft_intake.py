import unittest
from web_draft_intake import inspect_web_draft

def sample():
    return {
        "version":"oppo-quote-pmp-web-draft-v1",
        "status":"HOLD_CONTACT_ACCOUNT_QUOTE_REVIEW",
        "request":{"contact_email":"demo@example.org","service":"PMP","sequencing_mode":"PE250","sample_count":5,"depth_per_sample":1,"depth_unit":"M reads"},
        "summary":{"nominal_total_depth":5,"depth_unit":"M reads","reads_basis":"UNSPECIFIED_WHETHER_READS_OR_READ_PAIRS"},
        "required_checks":["exact_contact_email_identity","account_record_id_and_contact_lookup","existing_opportunity_and_quotation_duplicates","approved_opportunity_name_amount_stage_close_date","current_business_entity_promotion_type_valid_thru","verified_price_and_quote_lines","post_creation_native_006_parent_and_a0P_quote_links"],
        "salesforce_save_allowed":False,"opportunity_created":False,"quotation_created":False}

class IntakeTests(unittest.TestCase):
    def test_valid(self):
        self.assertFalse(inspect_web_draft(sample())["save_allowed"])
    def test_tampered_total(self):
        a=sample()
        a["summary"]["nominal_total_depth"]=6
        with self.assertRaises(ValueError):
            inspect_web_draft(a)
    def test_wrong_units(self):
        a=sample()
        a["request"]["depth_unit"]="Gb"
        with self.assertRaises(ValueError):
            inspect_web_draft(a)
    def test_unexpected_field(self):
        a=sample()
        a["new_field"]=1
        with self.assertRaises(ValueError):
            inspect_web_draft(a)
    def test_repeated(self):
        self.assertEqual([inspect_web_draft(sample()) for _ in range(3)],[inspect_web_draft(sample()) for _ in range(3)])
