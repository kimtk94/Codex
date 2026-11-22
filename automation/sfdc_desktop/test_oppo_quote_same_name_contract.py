"""Synthetic-only tests: no authentication, network or Salesforce writes."""
import unittest

from oppo_quote_same_name_contract import (
    OpportunitySnapshot, QuoteSnapshot, ManualReview,
    match_single_product_quote, match_identical_name_quote,
    dryrun_after_read_only_identity_check,
    verify_live_quotation_relationship,
    validate_opportunity_clone_preflight,
)

OPPO = OpportunitySnapshot(
    "006000000000AAA",
    "Korea-Synthetic Univ.-5-PMP-250PE-1M-WOBI-TestContact",
)
QUOTE = QuoteSnapshot(
    "a0P000000000AAA",
    OPPO.name + "-AMEA2026110301",
    "AMEA2026110301",
    OPPO.name,
    1,
)


EVIDENCE = {
    "source": "SFDC_LIGHTNING_DETAIL",
    "quote_object": "Quotation__c",
    "quotation_record_id": QUOTE.record_id,
    "parent_opportunity_id": OPPO.record_id,
    "quotation_account_id": "001000000000AAA",
    "opportunity_account_id": "001000000000AAA",
    "contact_account_id": "001000000000AAA",
    "quotation_contact_id": "003000000000AAA",
    "opportunity_main_contact_id": "003000000000AAA",
}


def evidence(**changes):
    return {**EVIDENCE, **changes}


def run(q=QUOTE, o=None):
    return match_single_product_quote(q, [OPPO] if o is None else o)


def replace(**overrides):
    d = vars(QUOTE).copy()
    d.update(overrides)
    return QuoteSnapshot(**d)


class OppoQuoteIdenticalOnlyContractTests(unittest.TestCase):
    def test_clone_with_verified_contact_and_name_field_passes(self):
        self.assertTrue(validate_opportunity_clone_preflight(
            "Opportunity Clone - New Opportunity",
            name_input_visible=True,
            main_contact_link_verified=True,
        ))

    def test_clone_main_contact_reference_error_blocks(self):
        page = ("Looks like there's a problem. "
                "Unable to find the record referenced by "
                "Opportunity.Main_Contact__c in null: TEST_ID")
        with self.assertRaises(ManualReview):
            validate_opportunity_clone_preflight(
                page, name_input_visible=False,
                main_contact_link_verified=False,
            )

    def test_clone_missing_name_field_blocks_without_guessing(self):
        with self.assertRaises(ManualReview):
            validate_opportunity_clone_preflight(
                "Opportunity Clone",
                name_input_visible=False, main_contact_link_verified=True,
            )

    def test_clone_unverified_main_contact_blocks_even_when_name_visible(self):
        with self.assertRaises(ManualReview):
            validate_opportunity_clone_preflight(
                "Opportunity Clone",
                name_input_visible=True, main_contact_link_verified=False,
            )

    def test_multiple_products_still_train_name_only(self):
        q = replace(product_record_count=2)
        candidate = match_identical_name_quote(q, [OPPO])
        self.assertEqual(candidate["learning_scope"], "NAME_AND_PARENT_ONLY")
        self.assertEqual(candidate["product_record_count"], 2)

    def test_zero_product_still_train_name_only(self):
        q = replace(product_record_count=0)
        candidate = match_identical_name_quote(q, [OPPO])
        self.assertEqual(candidate["learning_scope"], "NAME_AND_PARENT_ONLY")
        self.assertEqual(candidate["product_record_count"], 0)

    def test_multi_product_name_only_cannot_enter_basic_dryrun(self):
        candidate = match_identical_name_quote(
            replace(product_record_count=2), [OPPO]
        )
        with self.assertRaises(ManualReview):
            dryrun_after_read_only_identity_check(candidate, OPPO.record_id)

    def test_one_product_still_basic_dryrun(self):
        candidate = run()
        self.assertEqual(candidate["learning_scope"], "SINGLE_PRODUCT_DRY_RUN")

    def test_valid_strict_match(self):
        r = run()
        self.assertEqual(r["source_opportunity_id"], OPPO.record_id)
        self.assertFalse(r["save_clicked"])
        self.assertFalse(r["create_opportunity"])
        self.assertFalse(r["create_quote"])
        self.assertFalse(r["send_quote"])

    def test_live_parent_link_verification_pass(self):
        r = dryrun_after_read_only_identity_check(run(), OPPO.record_id, relationship_evidence=evidence())
        self.assertTrue(r["actual_parent_verified"])
        self.assertTrue(r["actual_quotation_account_contact_verified"])
        self.assertEqual(r["mode"], "FORM_DRY_RUN_NO_SAVE")
        self.assertFalse(r["save_clicked"])


    def test_missing_direct_lightning_relationship_readback_blocks(self):
        with self.assertRaises(ManualReview):
            dryrun_after_read_only_identity_check(run(), OPPO.record_id)

    def test_actual_custom_quotation_account_contact_passes(self):
        self.assertTrue(verify_live_quotation_relationship(run(), evidence()))

    def test_standard_salesforce_quote_object_blocks(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(run(), evidence(quote_object="Quote"))

    def test_stale_sheet_source_cannot_substitute_for_lightning(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(run(), evidence(source="GOOGLE_SHEETS"))

    def test_missing_quote_parent_link_blocks(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(run(), evidence(parent_opportunity_id=""))

    def test_quotation_account_and_parent_account_must_match(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(
                run(), evidence(quotation_account_id="001000000000AAB")
            )

    def test_opportunity_account_and_contact_account_must_match(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(
                run(), evidence(contact_account_id="001000000000AAB")
            )

    def test_quotation_contact_and_opportunity_contact_must_match(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(
                run(), evidence(quotation_contact_id="003000000000AAB")
            )

    def test_quotation_record_id_must_match_selected_example(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(
                run(), evidence(quotation_record_id="a0P000000000AAB")
            )

    def test_fake_short_account_id_blocks(self):
        with self.assertRaises(ManualReview):
            verify_live_quotation_relationship(
                run(), evidence(opportunity_account_id="001fake")
            )


    def test_live_parent_link_mismatch_blocks(self):
        with self.assertRaises(ManualReview):
            dryrun_after_read_only_identity_check(run(), "006000000000AAB")

    def test_missing_amea_number_blocks(self):
        with self.assertRaises(ManualReview):
            run(replace(name=OPPO.name))

    def test_quote_number_mismatch_blocks(self):
        with self.assertRaises(ManualReview):
            run(replace(quote_number="AMEA2026110399"))

    def test_quote_name_only_looks_similar_blocks(self):
        with self.assertRaises(ManualReview):
            run(replace(name=OPPO.name + "-extra-AMEA2026110301"))

    def test_different_parent_name_blocks(self):
        with self.assertRaises(ManualReview):
            run(replace(opportunity_name="Korea-Synthetic Univ.-8-WGS"))

    def test_no_opportunity_blocks(self):
        with self.assertRaises(ManualReview):
            run(o=[])

    def test_ambiguous_opportunity_name_blocks(self):
        duplicate = OpportunitySnapshot("006000000000AAB", OPPO.name)
        with self.assertRaises(ManualReview):
            run(o=[OPPO, duplicate])

    def test_quote_without_product_blocks(self):
        with self.assertRaises(ManualReview):
            run(replace(product_record_count=0))

    def test_multi_product_quote_blocks(self):
        with self.assertRaises(ManualReview):
            run(replace(product_record_count=2))

    def test_invalid_quote_id_blocks(self):
        with self.assertRaises(ManualReview):
            run(replace(record_id="a0L000000000AAA"))

    def test_opportunity_id_invalid_blocks(self):
        with self.assertRaises(ManualReview):
            run(o=[OpportunitySnapshot("003000000000AAA", OPPO.name)])

    def test_tampered_save_flag_blocks(self):
        candidate = run()
        candidate["save_clicked"] = True
        with self.assertRaises(ManualReview):
            dryrun_after_read_only_identity_check(candidate, OPPO.record_id)

    def test_tampered_create_quote_blocks(self):
        candidate = run()
        candidate["create_quote"] = True
        with self.assertRaises(ManualReview):
            dryrun_after_read_only_identity_check(candidate, OPPO.record_id)

    def test_quote_number_with_revision_suffix(self):
        number = "AMEA2026110301-01"
        quote = replace(name=OPPO.name + "-" + number, quote_number=number)
        self.assertEqual(run(quote)["quote_number"], number)

    def test_case_differences_not_silent_match(self):
        with self.assertRaises(ManualReview):
            run(replace(opportunity_name=OPPO.name.lower()))

    def test_no_false_positive_from_trailing_text(self):
        with self.assertRaises(ManualReview):
            run(replace(name=OPPO.name + "-AMEA2026110301-Invalid"))


if __name__ == "__main__":
    unittest.main()
