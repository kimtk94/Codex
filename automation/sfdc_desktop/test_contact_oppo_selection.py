"""Synthetic-only selection and linked-case regression. No customer records."""
import unittest
from contact_oppo_selection import select_contact, eligible_pair

C1="003000000000001AAA"
C2="003000000000002AAA"
A1="001000000000001AAA"
A2="001000000000002AAA"
O1="006000000000001AAA"
O2="006000000000002AAA"

def row(cid=C1,aid=A1,name="김민수",institution="서울대학교",opps=None):
    return {"name":name,"contact_id":cid,"account_id":aid,
            "institution":institution,"opportunity_ids":[O1] if opps is None else opps}

def pair():
    return {"independent_link_verified":True,"opportunity_id":O1,
            "quote_parent_opportunity_id":O1,"institution":"서울대학교",
            "service_count":1,"opportunity_service":"PMP","quote_service":"PMP"}

class ContactSelectionTests(unittest.TestCase):
    def test_korean_spacing_and_unicode_normalization(self):
        result=select_contact("  김민수  ",[row(name="김민수")])
        self.assertEqual(result["status"],"CANDIDATE_REQUIRES_LIVE_SFDC_VERIFICATION")
        self.assertFalse(result["save_allowed"])
    def test_homonym_requires_institution(self):
        rows=[row(),row(C2,A2,institution="연세대학교")]
        self.assertEqual(select_contact("김민수",rows)["status"],
                         "HOLD_SELECT_EXACT_INSTITUTION_AND_CONTACT")
        result=select_contact("김민수",rows,"연세대학교")
        self.assertEqual(len(result["candidates"]),1)
        self.assertEqual(result["candidates"][0]["contact_id"],C2)
    def test_same_institution_homonym_still_ambiguous(self):
        rows=[row(),row(C2,A1)]
        self.assertEqual(select_contact("김민수",rows,"서울대학교")["status"],
                         "HOLD_SELECT_EXACT_INSTITUTION_AND_CONTACT")
    def test_no_opportunity_contact_ignored(self):
        self.assertEqual(select_contact("김민수",[row(opps=[])])["status"],"HOLD_NO_ELIGIBLE_CONTACT")
    def test_invalid_ids_never_selected(self):
        self.assertEqual(select_contact("김민수",[row(cid="not-contact")])["status"],"HOLD_NO_ELIGIBLE_CONTACT")
    def test_excluded_accounts(self):
        for institution in ("KAIST","한국과학기술원","한남대","한남대학교"):
            with self.subTest(institution=institution):
                self.assertEqual(select_contact("김민수",[row(institution=institution)])["status"],
                                 "HOLD_NO_ELIGIBLE_CONTACT")
    def test_does_not_fuzzy_merge_institution(self):
        result=select_contact("김민수",[row(institution="서울대학교")],"서울대")
        self.assertEqual(result["status"],"HOLD_NO_ELIGIBLE_CONTACT")
    def test_does_not_fuzzy_merge_name(self):
        result=select_contact("민수",[row()])
        self.assertEqual(result["status"],"HOLD_NO_ELIGIBLE_CONTACT")
    def test_duplicate_identical_rows_deduplicated(self):
        self.assertEqual(len(select_contact("김민수",[row(),row()])["candidates"]),1)
    def test_invalid_source_fail_closed(self):
        self.assertEqual(select_contact("김민수",None)["status"],"HOLD_INVALID_SOURCE")
        self.assertEqual(select_contact("",[row()])["status"],"HOLD_NAME_REQUIRED")
    def test_three_repeat_identical_candidates(self):
        rows=[row(),row(C2,A2,institution="연세대학교")]
        outputs=[select_contact("김민수",rows) for _ in range(3)]
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(outputs[1],outputs[2])

class LinkedPairTests(unittest.TestCase):
    def test_matching_single_service_still_only_pattern(self):
        self.assertEqual(eligible_pair(pair()),"ELIGIBLE_PATTERN_ONLY_NO_SAVE")
    def test_name_matching_without_native_relation_is_not_enough(self):
        d=pair();d["independent_link_verified"]=False
        self.assertEqual(eligible_pair(d),"HOLD_UNVERIFIED_NATIVE_RELATION")
    def test_parent_mismatch(self):
        d=pair();d["quote_parent_opportunity_id"]=O2
        self.assertEqual(eligible_pair(d),"HOLD_PARENT_RELATION_MISMATCH")
    def test_mixed_services(self):
        d=pair();d["service_count"]=2
        self.assertEqual(eligible_pair(d),"HOLD_MIXED_OR_MISMATCHED_SERVICES")
    def test_service_mismatch(self):
        d=pair();d["quote_service"]="mRNA"
        self.assertEqual(eligible_pair(d),"HOLD_MIXED_OR_MISMATCHED_SERVICES")
    def test_excluded_account(self):
        d=pair();d["institution"]="한남대학교"
        self.assertEqual(eligible_pair(d),"EXCLUDED_ACCOUNT")
    def test_zero_service(self):
        d=pair();d["opportunity_service"]="";d["quote_service"]=""
        self.assertEqual(eligible_pair(d),"HOLD_MISSING_SERVICE")

if __name__=="__main__":
    unittest.main()
