"""Additional edge cases for Lead Convert. Synthetic records only."""
import unittest
from lead_convert_account_contact_contract import (
    AccountCandidate, ConversionHold, plan_account_contact_only
)

A = AccountCandidate("001000000000AAA", "Synthetic Institute")


def plan(first="김민수", last="KimMinSu", accounts=None, selected=None, **opts):
    return plan_account_contact_only(
        [A] if accounts is None else accounts,
        A.record_id if selected is None else selected,
        first, last, **opts
    )


class LeadConvertEdgeTests(unittest.TestCase):
    def test_trim_names(self):
        p = plan(first="  김민수  ", last="  KimMinSu  ")
        self.assertEqual(p["contact_first_name_korean"], "김민수")
        self.assertEqual(p["contact_last_name_english"], "KimMinSu")

    def test_support_english_name_with_spaces(self):
        self.assertEqual(plan(last="Kim Min Su")["contact_last_name_english"], "Kim Min Su")

    def test_support_romanized_name_with_apostrophe(self):
        self.assertEqual(plan(last="O'Neill")["contact_last_name_english"], "O'Neill")

    def test_support_18_character_account_id(self):
        acct = AccountCandidate("001000000000AAA123", "Synthetic Institute")
        self.assertEqual(
            plan(accounts=[acct], selected=acct.record_id)["existing_account_id"],
            acct.record_id,
        )

    def test_reject_non_account_id_prefix(self):
        with self.assertRaises(ConversionHold):
            plan(selected="003000000000AAA")

    def test_reject_account_name_without_id(self):
        with self.assertRaises(ConversionHold):
            plan(selected="Synthetic Institute")

    def test_reject_no_account_suggestions(self):
        with self.assertRaises(ConversionHold):
            plan(accounts=[])

    def test_reject_blank_korean_first_name(self):
        with self.assertRaises(ConversionHold):
            plan(first=" ")

    def test_reject_blank_english_last_name(self):
        with self.assertRaises(ConversionHold):
            plan(last=" ")

    def test_reject_english_first_name_even_when_last_name_good(self):
        with self.assertRaises(ConversionHold):
            plan(first="John")

    def test_reject_korean_last_name_even_when_first_name_good(self):
        with self.assertRaises(ConversionHold):
            plan(last="김민수")

    def test_reject_duplicate_contact_two_matches(self):
        with self.assertRaises(ConversionHold):
            plan(existing_contact_match_count=2)

    def test_reject_new_account_candidate_even_when_id_wellformed(self):
        with self.assertRaises(ConversionHold):
            plan(accounts=[AccountCandidate(A.record_id, A.institution_name, False)])

    def test_strict_no_opportunity_required(self):
        with self.assertRaises(ConversionHold):
            plan(no_opportunity_checkbox_checked=False)

    def test_never_submit_even_valid_preview(self):
        p = plan()
        self.assertFalse(p["submit_convert"])
        self.assertFalse(p["create_opportunity"])
        self.assertFalse(p["create_account"])


if __name__ == "__main__":
    unittest.main()
