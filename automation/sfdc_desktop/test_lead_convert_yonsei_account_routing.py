"""Synthetic-only Yonsei Account routing tests; no Salesforce writes."""
import unittest

from lead_convert_account_contact_contract import (
    AccountCandidate,
    ConversionHold,
    recommend_existing_account,
    plan_lead_convert_with_routing,
)

GENERAL = AccountCandidate(
    "001000000000AAA",
    "연세대학교 산학협력단 Yonsei University Industry-Academic Cooperation Foundation",
)
MEDICAL = AccountCandidate(
    "001000000000AAB",
    "연세대학교 의료원 산학협력단 Yonsei University Health System Industry-University Cooperation Foundation",
)
HOSPITAL = AccountCandidate(
    "001000000000AAC",
    "연세대학교 의료원 Yonsei University Health System (YUHS)",
)
MIRAE = AccountCandidate(
    "001000000000AAD",
    "Yonsei University Mirae Campus University-Industry Foundation",
)
GENERIC = AccountCandidate("001000000000AAE", "Yonsei University")
FOUNDATIONS = [GENERAL, MEDICAL, HOSPITAL, MIRAE, GENERIC]


class YonseiDomainAccountRoutingTests(unittest.TestCase):
    def test_yuhs_ac_routes_medical(self):
        self.assertEqual(
            recommend_existing_account(FOUNDATIONS, "연세대학교", email="person@yuhs.ac"),
            MEDICAL.record_id,
        )

    def test_yuhs_ac_kr_routes_medical(self):
        self.assertEqual(
            recommend_existing_account(FOUNDATIONS, "Yonsei University", email="person@yuhs.ac.kr"),
            MEDICAL.record_id,
        )

    def test_yuhs_yonsei_ac_kr_precedence_medical(self):
        self.assertEqual(
            recommend_existing_account(FOUNDATIONS, "연세대학교", email="person@yuhs.yonsei.ac.kr"),
            MEDICAL.record_id,
        )

    def test_yonsei_ac_kr_routes_general(self):
        self.assertEqual(
            recommend_existing_account(FOUNDATIONS, "연세대", email="person@yonsei.ac.kr"),
            GENERAL.record_id,
        )

    def test_yonsei_edu_routes_general(self):
        self.assertEqual(
            recommend_existing_account(FOUNDATIONS, "Yonsei University", email="person@yonsei.edu"),
            GENERAL.record_id,
        )

    def test_subdomains_of_known_institutional_hosts(self):
        self.assertEqual(
            recommend_existing_account(FOUNDATIONS, "연세대학교", email="person@mail.yuhs.ac.kr"),
            MEDICAL.record_id,
        )

    def test_unrecognized_domain_holds(self):
        with self.assertRaises(ConversionHold):
            recommend_existing_account(FOUNDATIONS, "연세대학교", email="person@gmail.com")

    def test_missing_domain_holds(self):
        with self.assertRaises(ConversionHold):
            recommend_existing_account(FOUNDATIONS, "연세대학교")

    def test_domain_keyword_in_username_does_not_count(self):
        with self.assertRaises(ConversionHold):
            recommend_existing_account(FOUNDATIONS, "연세대학교", email="yuhs@outlook.com")

    def test_substring_impostor_domain_holds(self):
        with self.assertRaises(ConversionHold):
            recommend_existing_account(FOUNDATIONS, "연세대학교", email="x@fakeyuhs.ac.kr")

    def test_medical_account_not_in_suggestions_holds(self):
        with self.assertRaises(ConversionHold):
            recommend_existing_account([GENERAL, HOSPITAL], "연세대학교", email="x@yuhs.ac")

    def test_general_account_not_in_suggestions_holds(self):
        with self.assertRaises(ConversionHold):
            recommend_existing_account([MEDICAL, GENERIC], "연세대학교", email="x@yonsei.ac.kr")

    def test_duplicate_medical_foundations_hold(self):
        second = AccountCandidate("001000000000AAF", MEDICAL.institution_name)
        with self.assertRaises(ConversionHold):
            recommend_existing_account(FOUNDATIONS + [second], "연세대학교", email="x@yuhs.ac")

    def test_create_new_medical_option_is_excluded(self):
        result = recommend_existing_account(
            [GENERAL, AccountCandidate("001000000000AAF", MEDICAL.institution_name, False), MEDICAL],
            "연세대학교", email="x@yuhs.ac",
        )
        self.assertEqual(result, MEDICAL.record_id)

    def test_contact_only_plan_binds_selected_account_medical(self):
        plan = plan_lead_convert_with_routing(
            FOUNDATIONS, company="연세대학교", email="x@yuhs.ac",
            korean_name="김민수", english_name="KimMinSu",
        )
        self.assertEqual(plan["existing_account_id"], MEDICAL.record_id)
        self.assertFalse(plan["create_account"])
        self.assertTrue(plan["create_contact"])
        self.assertFalse(plan["create_opportunity"])
        self.assertFalse(plan["submit_convert"])

    def test_contact_only_plan_binds_selected_account_general(self):
        plan = plan_lead_convert_with_routing(
            FOUNDATIONS, company="연세대학교", email="x@yonsei.ac.kr",
            korean_name="김민수", english_name="KimMinSu",
        )
        self.assertEqual(plan["existing_account_id"], GENERAL.record_id)

    def test_route_refuses_contact_duplicate(self):
        with self.assertRaises(ConversionHold):
            plan_lead_convert_with_routing(
                FOUNDATIONS, company="연세대학교", email="x@yonsei.ac.kr",
                korean_name="김민수", english_name="KimMinSu",
                existing_contact_match_count=1,
            )

    def test_route_refuses_opportunity_creation(self):
        with self.assertRaises(ConversionHold):
            plan_lead_convert_with_routing(
                FOUNDATIONS, company="연세대학교", email="x@yuhs.ac",
                korean_name="김민수", english_name="KimMinSu",
                no_opportunity_checkbox_checked=False,
            )


if __name__ == "__main__":
    unittest.main()
