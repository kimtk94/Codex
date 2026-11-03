"""Synthetic, offline checks for Oppo-linked Contact-only lookup; no PII."""
import unittest

from oppo_linked_contact_contract import make_oppo_linked_contact_index

OPPO1 = "006000000000AAA"
OPPO2 = "006000000000AAB"
CON1 = "003000000000AAA"
CON2 = "003000000000AAB"
ACC1 = "001000000000AAA"
ACC2 = "001000000000AAB"


def edge(o=OPPO1, c=CON1, a=ACC1, institution="경북대학교 산학협력단"):
    return {"oppo_id": o, "main_contact_id": c,
            "account_id": a, "institution_name": institution}


def detail(name="김민수", account=ACC1, email="person@example.edu"):
    return {"korean_name": name, "account_id": account, "email": email}


class OppoContactIndexTests(unittest.TestCase):
    def test_one_linked_contact_ready_for_server_recheck(self):
        result = make_oppo_linked_contact_index([edge()], {CON1:detail()})
        self.assertEqual(len(result["index"]), 1)
        self.assertEqual(result["index"][0]["linked_opportunity_ids"], [OPPO1])
        self.assertFalse(result["index"][0]["save_allowed"])

    def test_two_oppos_for_one_contact_deduplicated(self):
        result = make_oppo_linked_contact_index(
            [edge(),edge(o=OPPO2)],{CON1:detail()})
        self.assertEqual(len(result["index"]), 1)
        self.assertEqual(result["index"][0]["linked_opportunity_ids"], [OPPO1,OPPO2])

    def test_contacts_without_opportunities_never_appear(self):
        result = make_oppo_linked_contact_index([], {CON1:detail()})
        self.assertEqual(result["index"], [])

    def test_invalid_opportunity_id_is_held(self):
        result = make_oppo_linked_contact_index(
            [edge(o="NO_OPPO")],{CON1:detail()})
        self.assertEqual(len(result["index"]),0)
        self.assertEqual(result["hold"][0]["status"],"HOLD_INVALID_REFERENCE")

    def test_missing_contact_record_is_held(self):
        result = make_oppo_linked_contact_index([edge()], {})
        self.assertEqual(len(result["index"]),0)
        self.assertEqual(result["hold"][0]["status"],"HOLD_CONTACT_DETAILS_NOT_VERIFIED")

    def test_account_mismatch_is_held(self):
        result = make_oppo_linked_contact_index([edge()], {CON1:detail(account=ACC2)})
        self.assertEqual(result["hold"][0]["status"],"HOLD_CONTACT_ACCOUNT_RELATIONSHIP")

    def test_inconsistent_opp_account_links_are_held(self):
        result = make_oppo_linked_contact_index(
            [edge(),edge(o=OPPO2,a=ACC2)],{CON1:detail()})
        self.assertEqual(result["hold"][0]["status"],"HOLD_CONFLICTING_OPPO_ACCOUNTS")

    def test_exclude_kaist(self):
        result = make_oppo_linked_contact_index(
            [edge(institution="KAIST Korea Advanced Institute of Science")],{CON1:detail()})
        self.assertEqual(len(result["index"]),0)
        self.assertEqual(result["skip"][0]["status"],"SKIP_KAIST")

    def test_exclude_hannam(self):
        result = make_oppo_linked_contact_index(
            [edge(institution="한남대학교 산학협력단")],{CON1:detail()})
        self.assertEqual(result["skip"][0]["status"],"SKIP_HANNAM")

    def test_institution_disambiguates_korean_homonyms(self):
        result = make_oppo_linked_contact_index(
            [edge(),edge(o=OPPO2,c=CON2,a=ACC2,institution="연세대학교 산학협력단")],
            {CON1:detail(),CON2:detail(account=ACC2,email="person2@example.edu")})
        self.assertEqual(len(result["index"]),2)
        self.assertEqual(len({r["institution_name"] for r in result["index"]}),2)

    def test_same_name_same_institution_is_held(self):
        result = make_oppo_linked_contact_index(
            [edge(),edge(o=OPPO2,c=CON2)],
            {CON1:detail(),CON2:detail(email="person2@example.edu")})
        self.assertEqual(len(result["index"]),0)
        self.assertEqual(len([x for x in result["hold"] if x["status"]=="HOLD_SAME_NAME_SAME_ACCOUNT"]),2)

    def test_missing_korean_name_is_held(self):
        result = make_oppo_linked_contact_index([edge()],{CON1:detail(name="John Kim")})
        self.assertEqual(result["hold"][0]["status"],"HOLD_KOREAN_NAME_OR_EMAIL")

    def test_invalid_email_is_held(self):
        result = make_oppo_linked_contact_index([edge()],{CON1:detail(email="not-email")})
        self.assertEqual(result["hold"][0]["status"],"HOLD_KOREAN_NAME_OR_EMAIL")

    def test_english_and_invalid_contact_id_are_held(self):
        result = make_oppo_linked_contact_index([edge(c="FAKE")],{})
        self.assertEqual(result["hold"][0]["status"],"HOLD_INVALID_REFERENCE")

    def test_duplicate_opp_link_never_duplicates_contact(self):
        result = make_oppo_linked_contact_index([edge(),edge()],{CON1:detail()})
        self.assertEqual(len(result["index"]),1)
        self.assertEqual(result["index"][0]["linked_opportunity_ids"],[OPPO1])


if __name__=="__main__":
    unittest.main()
