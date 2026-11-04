import unittest
from verify_one_to_one_quote_native_parents_private import (
    choose_verified_contact_cases, classify_native_parent,
)


def candidate(i,status="Need to submit",live=True):
    return {"quote_id":f"a0P{i:012d}AAA",
            "opportunity_id":f"006{i:012d}AAA",
            "quote_status":status,
            "known_contact_opportunity_live_evidence":live,
            "native_quote_parent_independently_live_verified":False,
            "salesforce_save_allowed":False}


class ParentProofTests(unittest.TestCase):
    def test_stratified_without_unverified_contacts(self):
        rows=[candidate(i) for i in range(4)]+[
            candidate(5,"Ready to send"),candidate(6,"Ready to send"),
            candidate(7,"Ready to send",False)]
        chosen=choose_verified_contact_cases(rows,2)
        self.assertEqual(len(chosen),4)
        self.assertEqual(sum(x["quote_status"]=="Ready to send" for x in chosen),2)

    def test_exact_quote_and_opportunity_ids_required(self):
        x=candidate(1)
        actual={"status":"QUOTE_NATIVE_PARENT_MATCH_REVIEW_COMPLETE",
                "parent_verified":True,"quote_id_verified":True,
                "opportunity_id_private":x["opportunity_id"],
                "quotation_id_private":x["quote_id"]}
        self.assertEqual(classify_native_parent(x,actual),"PASS_NATIVE_QUOTE_AND_PARENT_IDS")
        actual["quotation_id_private"]="a0P000000000002AAA"
        self.assertEqual(classify_native_parent(x,actual),"HOLD_QUOTE_ID_CONFLICT")

    def test_unproven_parent_still_hold(self):
        x=candidate(1)
        actual={"status":"HOLD_RELATED_COUNT_NOT_EXACTLY_ONE",
                "parent_verified":False,"quote_id_verified":False}
        self.assertTrue(classify_native_parent(x,actual).startswith("HOLD_"))

    def test_untrusted_saved_flag_excluded(self):
        x=candidate(1)
        x["salesforce_save_allowed"]=True
        self.assertEqual(choose_verified_contact_cases([x]),[])

    def test_deterministic_in_three_repeats(self):
        samples=[choose_verified_contact_cases([candidate(1),candidate(2)],2) for _ in range(3)]
        self.assertEqual(samples[0],samples[1])
        self.assertEqual(samples[1],samples[2])


if __name__=="__main__":
    unittest.main()
