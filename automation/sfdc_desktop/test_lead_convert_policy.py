"""Offline Lead conversion policy regression tests.

Run in the existing 3-pass sfdc-desktop-p0-tests GitHub Actions workflow.
"""
import unittest

from lead_convert_policy import (
    ACADEMIC_PI,
    build_contact_plan,
    cdms_sync_verified,
    english_full_name,
)


class LeadConvertPolicyTests(unittest.TestCase):
    def setUp(self):
        self.data = dict(
            korean_full_name="오준혁",
            romanized_surname="Oh",
            romanized_given_syllables=["Jun", "Hyeok"],
            verified_account_id="001TK0000129PdUYAU",
            org_type="Academic",
            job_options=["--None--", ACADEMIC_PI, "ACADEMIC:Lab Managers"],
            account_address=dict(
                street="100, Inha-ro, Michuhol-gu",
                city="Incheon",
                state="",
                postal_code="22212",
                country="Korea",
            ),
        )

    def test_name_format(self):
        self.assertEqual(english_full_name("oh", ["jun", "hyeok"]), "OhJunHyeok")

    def test_valid_conversion_uses_existing_account_and_no_opportunity(self):
        p = build_contact_plan(**self.data)
        self.assertEqual((p.first_name, p.last_name), ("오준혁", "OhJunHyeok"))
        self.assertEqual(p.job_function, ACADEMIC_PI)
        self.assertEqual(p.account_id, self.data["verified_account_id"])
        self.assertFalse(p.create_opportunity)
        self.assertEqual(p.shipping_street, self.data["account_address"]["street"])
        self.assertEqual(p.shipping_postal_code, "22212")

    def test_dont_guess_romanization(self):
        data = dict(self.data, romanized_given_syllables=[])
        # A surname alone is not a verified complete name.
        self.assertRaises(ValueError, build_contact_plan, **dict(data, romanized_surname=""))
        self.assertRaises(ValueError, english_full_name, "Oh", ["준혁"])

    def test_missing_account_is_blocked(self):
        self.assertRaises(ValueError, build_contact_plan, **dict(self.data, verified_account_id=""))

    def test_address_missing_is_blocked(self):
        address = dict(self.data["account_address"], country="")
        self.assertRaises(ValueError, build_contact_plan, **dict(self.data, account_address=address))

    def test_first_academic_option_must_be_pi(self):
        self.assertRaises(ValueError, build_contact_plan, **dict(
            self.data, job_options=["--None--", "ACADEMIC:Students (grad students)", ACADEMIC_PI]
        ))

    def test_cdms_requires_actual_id_after_success(self):
        self.assertTrue(cdms_sync_verified(sync_message="Sync completed", cms_contact_id="CP2026110500064"))
        self.assertFalse(cdms_sync_verified(sync_message="Sync completed", cms_contact_id=""))
        self.assertFalse(cdms_sync_verified(sync_message="Error", cms_contact_id="CP2026110500064"))


if __name__ == "__main__":
    unittest.main()
