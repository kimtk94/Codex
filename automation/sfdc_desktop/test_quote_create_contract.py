"""Pure synthetic safety tests for new Research-AMEA Quotation creation."""
import unittest

from quote_create_contract import (
    validate_quote_form, prepare_quote_request, compare_created_quotation,
    REQUIRED_UI_PICKLISTS,
)

PARENT = "006000000000000AAA"
QUOTE = "a0P000000000000AAA"
BUSINESS = "Opp-2099-01-01-765432"
QID = "QID-2099-01-01-123456"


def form():
    return {
        "screen": "New Quotation: Research-AMEA",
        "record_type": "Research-AMEA",
        "record_type_selected_explicitly": True,
        "form_opened_from_exact_opportunity_related": True,
        "unique_quotation_name_textbox": True,
        "unique_cancel_button": True,
        "opportunity_selected": True,
        "opportunity_lookup_readonly": True,
        "opportunity_name_matches_verified_parent": True,
        "save_clicked": False,
        "required_picklist_controls": {
            key: {"count": 1, "aria_required": True, "enabled": True}
            for key in REQUIRED_UI_PICKLISTS
        },
    }


def parent():
    return {
        "opportunity_record_id": PARENT,
        "business_opportunity_id": BUSINESS,
        "parent_verified_from_salesforce_ui": True,
    }


def quote_request():
    return {
        "request_uid": "REQ-quote-12345678",
        "record_type": "Research-AMEA",
        "parent_opportunity_record_id": PARENT,
        "parent_business_opportunity_id": BUSINESS,
        "reviewed_current_quote_values": True,
        "save_allowed": False,
        "values": {
            "Quotation Name": "Korea-test-Quote",
            "Business Entity": "synthetic-entity",
            "Promotion Type": "synthetic-promotion",
            "Valid Thru": "synthetic-approved-option",
        },
    }


def created():
    return {
        "quotation_record_id": QUOTE,
        "qid": QID,
        "parent_opportunity_record_id": PARENT,
        "parent_business_opportunity_id": BUSINESS,
        "related_list_quotation_record_id": QUOTE,
        "quotation_detail_record_id": QUOTE,
        "quotation_record_type": "Research-AMEA",
        "related_list_matching_link_count": 1,
    }


class QuoteFormContractTests(unittest.TestCase):
    def test_realistic_form_shape_is_valid(self):
        self.assertTrue(validate_quote_form(form()))

    def test_quote_parent_must_be_selected(self):
        f = form()
        f["opportunity_selected"] = False
        with self.assertRaises(ValueError):
            validate_quote_form(f)

    def test_quote_parent_name_mismatch_fails(self):
        f = form()
        f["opportunity_name_matches_verified_parent"] = False
        with self.assertRaises(ValueError):
            validate_quote_form(f)

    def test_cancel_button_mandatory(self):
        f = form()
        f["unique_cancel_button"] = False
        with self.assertRaises(ValueError):
            validate_quote_form(f)

    def test_wrong_quote_record_type_fails(self):
        f = form()
        f["record_type"] = "AMEA Agreement"
        with self.assertRaises(ValueError):
            validate_quote_form(f)

    def test_create_form_must_have_all_required_picklists(self):
        f = form()
        del f["required_picklist_controls"]["Promotion Type"]
        with self.assertRaises(ValueError):
            validate_quote_form(f)

    def test_disabled_required_field_fails(self):
        f = form()
        f["required_picklist_controls"]["Valid Thru"]["enabled"] = False
        with self.assertRaises(ValueError):
            validate_quote_form(f)

    def test_form_that_saved_is_not_a_no_save_audit(self):
        f = form()
        f["save_clicked"] = True
        with self.assertRaises(ValueError):
            validate_quote_form(f)


class QuoteRequestTests(unittest.TestCase):
    def test_reviewed_quote_never_grants_save(self):
        result = prepare_quote_request(quote_request(), parent())
        self.assertEqual(result["status"], "QUOTE_REVIEWED_NOT_SAVED")
        self.assertFalse(result["save_allowed"])
        self.assertFalse(result["salesforce_quote_created"])
        self.assertEqual(len(result["quote_intent_fingerprint"]), 64)

    def test_missing_human_review_fails(self):
        r = quote_request()
        r["reviewed_current_quote_values"] = False
        with self.assertRaises(ValueError):
            prepare_quote_request(r, parent())

    def test_wrong_parent_native_id_fails(self):
        r = quote_request()
        r["parent_opportunity_record_id"] = "006000000000001AAA"
        with self.assertRaises(ValueError):
            prepare_quote_request(r, parent())

    def test_business_number_not_a_native_parent_id(self):
        r = quote_request()
        r["parent_opportunity_record_id"] = BUSINESS
        with self.assertRaises(ValueError):
            prepare_quote_request(r, parent())

    def test_missing_parent_ui_proof_fails(self):
        p = parent()
        p["parent_verified_from_salesforce_ui"] = False
        with self.assertRaises(ValueError):
            prepare_quote_request(quote_request(), p)

    def test_unreviewed_missing_entity_fails(self):
        r = quote_request()
        del r["values"]["Business Entity"]
        with self.assertRaises(ValueError):
            prepare_quote_request(r, parent())

    def test_quote_name_empty_fails(self):
        r = quote_request()
        r["values"]["Quotation Name"] = ""
        with self.assertRaises(ValueError):
            prepare_quote_request(r, parent())

    def test_unknown_extra_field_fails(self):
        r = quote_request()
        r["values"]["Currency"] = "USD"
        with self.assertRaises(ValueError):
            prepare_quote_request(r, parent())

    def test_save_enabled_fails(self):
        r = quote_request()
        r["save_allowed"] = True
        with self.assertRaises(ValueError):
            prepare_quote_request(r, parent())

    def test_idempotent_same_change_intent(self):
        a = prepare_quote_request(quote_request(), parent())
        r = quote_request()
        r["request_uid"] = "REQ-quote-87654321"
        b = prepare_quote_request(r, parent())
        self.assertEqual(a["quote_intent_fingerprint"], b["quote_intent_fingerprint"])


class CreatedQuoteLinkTests(unittest.TestCase):
    def test_matching_triplicate_links_still_require_manual_review(self):
        self.assertEqual(compare_created_quotation(parent(), created()),
                         "QUOTE_LINK_CONTENT_MATCHES_MANUAL_REVIEW_REQUIRED")

    def test_wrong_quotation_child_record_fails(self):
        c = created()
        c["quotation_detail_record_id"] = "a0P000000000001AAA"
        self.assertEqual(compare_created_quotation(parent(), c),
                         "HOLD_PARENT_OR_RELATED_LINK_MISMATCH")

    def test_wrong_parent_fails(self):
        c = created()
        c["parent_opportunity_record_id"] = "006000000000001AAA"
        self.assertEqual(compare_created_quotation(parent(), c),
                         "HOLD_PARENT_OR_RELATED_LINK_MISMATCH")

    def test_duplicate_related_quote_links_fails(self):
        c = created()
        c["related_list_matching_link_count"] = 2
        self.assertEqual(compare_created_quotation(parent(), c),
                         "HOLD_DUPLICATE_OR_AMBIGUOUS_RELATED_LINK")

    def test_missing_qid_fails(self):
        c = created()
        c.pop("qid")
        self.assertEqual(compare_created_quotation(parent(), c),
                         "HOLD_QUOTE_IDENTITY_MISSING")

    def test_missing_created_quote_fails(self):
        self.assertEqual(compare_created_quotation(parent(), None),
                         "HOLD_CREATE_READBACK_MISSING")


if __name__ == "__main__":
    unittest.main()
