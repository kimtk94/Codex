"""Offline, synthetic-only customer identity packet boundary tests."""
import copy
import unittest

from validate_web_contact_review_packet import validate_review_packet,select_live_source_record

CONTACT={"name":"김민수","institution":"연세대학교",
         "contact_id":"003000000000001AAA","account_id":"001000000000001AAA",
         "contact_email":"synthetic@example.org","opportunity_ids":["006000000000001AAA"]}
DRAFT={"version":"oppo-quote-pmp-web-draft-v1",
       "status":"HOLD_CONTACT_ACCOUNT_QUOTE_REVIEW",
       "request":{"contact_email":CONTACT["contact_email"],"service":"PMP",
                  "sequencing_mode":"PE250","sample_count":5,
                  "depth_per_sample":1,"depth_unit":"M reads"},
       "summary":{"nominal_total_depth":5,"depth_unit":"M reads",
                  "reads_basis":"UNSPECIFIED_WHETHER_READS_OR_READ_PAIRS"},
       "required_checks":["exact_contact_email_identity",
                          "account_record_id_and_contact_lookup",
                          "existing_opportunity_and_quotation_duplicates",
                          "approved_opportunity_name_amount_stage_close_date",
                          "current_business_entity_promotion_type_valid_thru",
                          "verified_price_and_quote_lines",
                          "post_creation_native_006_parent_and_a0P_quote_links"],
       "salesforce_save_allowed":False,"opportunity_created":False,
       "quotation_created":False}
GATE={"contact_identity_live_verified":False,
      "account_identity_live_verified":False,
      "opportunity_duplicate_check_complete":False,
      "quote_price_and_product_verified":False,
      "salesforce_save_allowed":False}

def packet():
    return {"version":"oppo-quote-contact-review-v1",
            "source":"authorized_private_browser_json",
            "status":"HOLD_FRESH_SALESFORCE_IDENTITY_AND_PRICING",
            "selected_contact":copy.deepcopy(CONTACT),
            "draft":copy.deepcopy(DRAFT),
            "gate":copy.deepcopy(GATE)}


class BoundPacketTests(unittest.TestCase):
    def test_roster_match_no_save(self):
        out=validate_review_packet(packet(),[CONTACT])
        self.assertTrue(out["matched_private_roster"])
        self.assertFalse(out["live_identity_verified"])
        self.assertFalse(out["save_allowed"])
        self.assertEqual(out["sample_count"],5)
    def test_three_repeat_determinism(self):
        runs=[validate_review_packet(packet(),[CONTACT]) for _ in range(3)]
        self.assertEqual(runs[0],runs[1])
        self.assertEqual(runs[1],runs[2])
    def test_changed_email_fails_closed(self):
        x=packet()
        x["draft"]["request"]["contact_email"]="other@example.org"
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])
    def test_modified_account_id_cannot_be_bound(self):
        x=packet()
        x["selected_contact"]["account_id"]="001000000000002AAA"
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])
    def test_modified_opportunity_ids_fail(self):
        x=packet()
        x["selected_contact"]["opportunity_ids"]=["006000000000002AAA"]
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])
    def test_duplicate_contact_id_in_roster_blocks(self):
        with self.assertRaises(ValueError):
            validate_review_packet(packet(),[CONTACT,CONTACT])
    def test_identity_verified_true_tamper_fails(self):
        x=packet()
        x["gate"]["contact_identity_live_verified"]=True
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])
    def test_save_true_tamper_fails(self):
        x=packet()
        x["gate"]["salesforce_save_allowed"]=True
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])
    def test_created_true_tamper_fails(self):
        x=packet()
        x["draft"]["quotation_created"]=True
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])
    def test_unknown_field_fails(self):
        x=packet()
        x["approve"]=True
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])
    def test_roster_missing_fails(self):
        with self.assertRaises(ValueError):
            validate_review_packet(packet(),[])
    def test_quote_amount_injection_fails(self):
        x=packet()
        x["draft"]["request"]["amount"]=900000
        with self.assertRaises(ValueError):
            validate_review_packet(x,[CONTACT])


    def test_expanded_cohort_live_evidence_not_bound_to_old_180_snapshot(self):
        # Only a private previously-verified source can supply full bilingual
        # Contact label and the exact native Opportunity for new candidates.
        valid={**copy.deepcopy(CONTACT),
               "display_name":"김민수 KimMinSu",
               "opportunity_id":CONTACT["opportunity_ids"][0],
               "contact_detail_id_verified":True,
               "contact_account_link_verified":True,
               "opportunity_contact_link_verified":True,
               "contact_email_verified":True,
               "contact_display_name_verified":True}
        selected=select_live_source_record(packet(),[valid])
        self.assertIsNotNone(selected)
        self.assertEqual(selected["display_name"],"김민수 KimMinSu")
        self.assertEqual(selected["opportunity_id"],CONTACT["opportunity_ids"][0])

    def test_unapproved_source_evidence_never_becomes_live_record(self):
        valid={**copy.deepcopy(CONTACT),
               "display_name":"김민수 KimMinSu",
               "opportunity_id":CONTACT["opportunity_ids"][0],
               "contact_detail_id_verified":False,
               "contact_account_link_verified":True,
               "opportunity_contact_link_verified":True,
               "contact_email_verified":True,
               "contact_display_name_verified":True}
        self.assertIsNone(select_live_source_record(packet(),[valid]))

    def test_conflicting_private_evidence_never_silently_chooses_one(self):
        valid={**copy.deepcopy(CONTACT),
               "display_name":"김민수 KimMinSu",
               "opportunity_id":CONTACT["opportunity_ids"][0],
               "contact_detail_id_verified":True,
               "contact_account_link_verified":True,
               "opportunity_contact_link_verified":True,
               "contact_email_verified":True,
               "contact_display_name_verified":True}
        self.assertIsNone(select_live_source_record(packet(),[valid,valid]))

    def test_mismatched_account_in_historical_evidence_blocks_reuse(self):
        invalid={**copy.deepcopy(CONTACT),
                 "account_id":"001000000000002AAA",
                 "display_name":"김민수 KimMinSu",
                 "opportunity_id":CONTACT["opportunity_ids"][0],
                 "contact_detail_id_verified":True,
                 "contact_account_link_verified":True,
                 "opportunity_contact_link_verified":True,
                 "contact_email_verified":True,
                 "contact_display_name_verified":True}
        self.assertIsNone(select_live_source_record(packet(),[invalid]))


if __name__=="__main__":
    unittest.main()
