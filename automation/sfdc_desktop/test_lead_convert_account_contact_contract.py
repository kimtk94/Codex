import unittest

from lead_convert_account_contact_contract import (
    AccountCandidate, ConversionHold, plan_account_contact_only
)

ACCOUNT = AccountCandidate("001000000000AAA", "Synthetic Univ. Core")


def preview(**kwargs):
    return plan_account_contact_only(
        [ACCOUNT], ACCOUNT.record_id, "김민수", "KimMinSu", **kwargs
    )


class LeadConvertAccountContactContractTests(unittest.TestCase):
    def test_valid_account_contact_no_opportunity(self):
        result = preview()
        self.assertEqual(result["existing_account_id"], ACCOUNT.record_id)
        self.assertEqual(result["contact_first_name_korean"], "김민수")
        self.assertEqual(result["contact_last_name_english"], "KimMinSu")
        self.assertFalse(result["create_account"])
        self.assertTrue(result["create_contact"])
        self.assertFalse(result["create_opportunity"])
        self.assertFalse(result["submit_convert"])

    def test_blocks_create_new_account_suggestion(self):
        with self.assertRaises(ConversionHold):
            plan_account_contact_only(
                [AccountCandidate(ACCOUNT.record_id, "Synthetic", False)],
                ACCOUNT.record_id, "김민수", "KimMinSu"
            )

    def test_blocks_missing_account_selection(self):
        with self.assertRaises(ConversionHold):
            plan_account_contact_only([ACCOUNT], "001000000000AAB", "김민수", "KimMinSu")

    def test_blocks_duplicate_account_selection(self):
        with self.assertRaises(ConversionHold):
            plan_account_contact_only([ACCOUNT, ACCOUNT], ACCOUNT.record_id, "김민수", "KimMinSu")

    def test_blocks_unchecked_no_opportunity(self):
        with self.assertRaises(ConversionHold):
            preview(no_opportunity_checkbox_checked=False)

    def test_blocks_existing_contact_duplicate(self):
        with self.assertRaises(ConversionHold):
            preview(existing_contact_match_count=1)

    def test_blocks_wrong_firstname_script(self):
        with self.assertRaises(ConversionHold):
            plan_account_contact_only([ACCOUNT], ACCOUNT.record_id, "KimMinSu", "KimMinSu")

    def test_blocks_wrong_lastname_script(self):
        with self.assertRaises(ConversionHold):
            plan_account_contact_only([ACCOUNT], ACCOUNT.record_id, "김민수", "김민수")

    def test_blocks_existing_contact_option_when_create_requested(self):
        with self.assertRaises(ConversionHold):
            preview(contact_create_new_checked=False)


if __name__ == "__main__":
    unittest.main()
