"""Synthetic-only regression for Korean Contact aliases (no CRM data)."""
import unittest

from build_private_contact_aliases import (
    korean_name_from_contact_label, verified_private_aliases,
)

C1="003000000000001AAA"
C2="003000000000002AAA"
A1="001000000000001AAA"
A2="001000000000002AAA"
O1="006000000000001AAA"


def row(display="김민수 KimMinSu", cid=C1, aid=A1, institution="서울대학교"):
    return {"display_name":display, "contact_id":cid, "account_id":aid,
            "institution":institution, "contact_email":"researcher@example.org",
            "opportunity_ids":[O1],
            "contact_detail_id_verified":True,
            "contact_account_link_verified":True,
            "opportunity_contact_link_verified":True,
            "contact_email_verified":True,
            "contact_display_name_verified":True}


class KoreanAliasTests(unittest.TestCase):
    def test_explicit_bilingual_name(self):
        self.assertEqual(korean_name_from_contact_label("김민수 KimMinSu"),"김민수")
    def test_hangul_name_alone(self):
        self.assertEqual(korean_name_from_contact_label("  김민수  "),"김민수")
    def test_romanized_name_not_inferred(self):
        self.assertIsNone(korean_name_from_contact_label("KimMinSu"))
    def test_ambiguous_mixed_label_held(self):
        for name in ("서울대학교 김민수","김민수 (유사)","KimMinSu 김민수","김민수 박영희",""):
            with self.subTest(name=name):
                self.assertIsNone(korean_name_from_contact_label(name))
    def test_verified_identity_produces_browser_compatible_row(self):
        result=verified_private_aliases([row()])
        self.assertEqual(result["records"][0]["name"],"김민수")
        self.assertEqual(result["records"][0]["contact_id"],C1)
        self.assertEqual(result["records"][0]["opportunity_ids"],[O1])
        self.assertFalse(result["save_allowed"])
    def test_missing_contact_detail_verification_is_hold(self):
        x=row()
        x["contact_detail_id_verified"]=False
        self.assertEqual(verified_private_aliases([x])["records"],[])
    def test_excluded_institutions(self):
        for name in ("KAIST","한국과학기술원","한남대","한남대학교"):
            with self.subTest(name=name):
                self.assertEqual(verified_private_aliases([row(institution=name)])["records"],[])
    def test_no_opportunity_not_selected(self):
        x=row()
        x["opportunity_ids"]=[]
        self.assertEqual(verified_private_aliases([x])["records"],[])
    def test_invalid_contact_id(self):
        self.assertEqual(verified_private_aliases([row(cid="random")])["records"],[])
    def test_two_same_name_contacts_remain_separate(self):
        result=verified_private_aliases([row(),row(cid=C2,aid=A2,institution="연세대학교")])
        self.assertEqual(len(result["records"]),2)
    def test_conflicting_same_contact_id_is_not_silently_chosen(self):
        result=verified_private_aliases([row(),row(display="김영희 KimYoungHee")])
        self.assertEqual(result["conflicting_identity_keys"],1)
        self.assertEqual(result["records"],[])
    def test_deduplicate_identical_source_rows(self):
        self.assertEqual(len(verified_private_aliases([row(),row()])["records"]),1)
    def test_three_repeat_determinism(self):
        outputs=[verified_private_aliases([row()]) for _ in range(3)]
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(outputs[1],outputs[2])
    def test_no_salesforce_save_in_any_output(self):
        result=verified_private_aliases([row()])
        self.assertEqual(result["save_allowed"],False)
        self.assertNotIn("salesforce_save_allowed",result["records"][0])
    def test_invalid_root_type_fails_closed(self):
        with self.assertRaises(ValueError):
            verified_private_aliases({"rows":[row()]})


if __name__=="__main__":
    unittest.main()
