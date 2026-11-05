import unittest
from verify_one_to_one_quote_native_parents_private import (
    choose_verified_contact_cases, classify_native_parent, select_remaining_native_cases,
)


def candidate(i,status="Need to submit",live=True):
    return {"quote_id":f"a0P{i:012d}AAA",
            "opportunity_id":f"006{i:012d}AAA",
            "quote_status":status,
            "known_contact_opportunity_live_evidence":live,
            "native_quote_parent_independently_live_verified":False,
            "single_product_snapshot":True,
            "snapshot_opportunity_and_contact_labels_match":True,
            "quote_name_unique_in_full_inventory":True,
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
        self.assertEqual(classify_native_parent(x,actual),"HOLD_RELATED_COUNT_NOT_EXACTLY_ONE")

    def test_untrusted_saved_flag_excluded(self):
        x=candidate(1)
        x["salesforce_save_allowed"]=True
        self.assertEqual(choose_verified_contact_cases([x]),[])

    def test_deterministic_in_three_repeats(self):
        samples=[choose_verified_contact_cases([candidate(1),candidate(2)],2) for _ in range(3)]
        self.assertEqual(samples[0],samples[1])
        self.assertEqual(samples[1],samples[2])


    def test_all_structural_can_verify_native_without_contact_pass(self):
        rows=[candidate(1,live=False),candidate(2,live=True)]
        chosen=select_remaining_native_cases(rows,[],all_structural=True,limit=10)
        self.assertEqual(len(chosen),2)
        self.assertFalse(chosen[0]["known_contact_opportunity_live_evidence"])
        self.assertTrue(all(r["salesforce_save_allowed"] is False for r in chosen))

    def test_mixed_product_or_nonunique_quote_never_native_checked(self):
        x=candidate(1,live=False)
        x["single_product_snapshot"]=False
        y=candidate(2,live=False)
        y["quote_name_unique_in_full_inventory"]=False
        z=candidate(3,live=False)
        z["snapshot_opportunity_and_contact_labels_match"]=False
        self.assertEqual(select_remaining_native_cases([x,y,z],[],all_structural=True),[])

    def test_invalid_record_id_never_navigated(self):
        x=candidate(1,live=False)
        x["quote_id"]="a0P_INVALID"
        self.assertEqual(select_remaining_native_cases([x],[],all_structural=True),[])

    def test_default_only_contact_link_verified(self):
        rows=[candidate(1,live=False),candidate(2,live=True)]
        selected=select_remaining_native_cases(rows,[],limit=10)
        self.assertEqual([r["quote_id"] for r in selected],[rows[1]["quote_id"]])

    def test_existing_attempt_not_rechecked_or_double_counted(self):
        rows=[candidate(1),candidate(2)]
        prior=[{"opportunity_id":rows[0]["opportunity_id"],"quote_id":rows[0]["quote_id"],
                "native_relation_status":"PASS_NATIVE_QUOTE_AND_PARENT_IDS"}]
        self.assertEqual(select_remaining_native_cases(rows,prior,all_structural=True,limit=10),rows[1:])

    def test_hold_already_attempted_is_not_silently_promoted(self):
        rows=[candidate(1)]
        prior=[{"opportunity_id":rows[0]["opportunity_id"],"quote_id":rows[0]["quote_id"],
                "native_relation_status":"HOLD_QUOTE_PARENT_ID_MISMATCH"}]
        self.assertEqual(select_remaining_native_cases(rows,prior,all_structural=True),[])

    def test_strict_max_readback_batch(self):
        rows=[candidate(i,live=False) for i in range(1,60)]
        self.assertEqual(len(select_remaining_native_cases(rows,[],all_structural=True,limit=25)),25)
        with self.assertRaises(ValueError):
            select_remaining_native_cases(rows,[],all_structural=True,limit=51)

    def test_three_repeat_native_selection_deterministic(self):
        rows=[candidate(i,live=False) for i in range(1,5)]
        checks=[select_remaining_native_cases(rows,[],all_structural=True,limit=3) for _ in range(3)]
        self.assertEqual(checks[0],checks[1])
        self.assertEqual(checks[1],checks[2])


if __name__=="__main__":
    unittest.main()
