"""Synthetic 1:1 Oppo/Quote learning shortlist with no native Save permission."""
import unittest

from audit_one_to_one_oppo_quote_shortlist_private import one_to_one_candidates


def quote(i,opp=1,name=None):
    on=name or f"Example University-{opp}-PMP-PE250-1M reads"
    return {"quote_id":f"a0P{i:012d}AAA",
            "oppo_id":f"006{opp:012d}AAA",
            "oppo_name":on,
            "quote_name":on+"-AMEA20260001",
            "quote_status":"Ready to send",
            "contact_display":"김민수 KimMinSu",
            "product_records":"1"}


def opportunity(i=1,name=None):
    return {"opportunity_id":f"006{i:012d}AAA",
            "opportunity_name":name or f"Example University-{i}-PMP-PE250-1M reads",
            "contact_display":"김민수 KimMinSu",
            "institution_hint":"Example University"}


def inventory(qs):
    records=[]
    for q in qs:
        c=[""]*16
        c[2]=q["quote_name"]
        c[4]=q["oppo_name"]
        c[5]=q["quote_status"]
        records.append({"id":q["quote_id"],"cells":c})
    return {"fully_enumerated":True,"limit_reached":False,"rows":records}


class UniqueQuoteLearningTests(unittest.TestCase):
    def test_single_product_and_unique_names_preliminary_not_approved(self):
        qs=[quote(1)]
        data=one_to_one_candidates(inventory(qs),qs,[opportunity(1)],[])
        self.assertEqual(data["summary"]["structurally_one_to_one_candidates"],1)
        self.assertEqual(data["summary"]["native_quote_parent_verified_for_candidates"],0)
        self.assertEqual(data["summary"]["auto_save_approved"],0)
        self.assertFalse(data["candidates"][0]["salesforce_save_allowed"])

    def test_multiple_quotes_same_opportunity_cannot_auto_train(self):
        qs=[quote(1),quote(2)]
        data=one_to_one_candidates(inventory(qs),qs,[opportunity(1)],[])
        self.assertEqual(data["summary"]["structurally_one_to_one_candidates"],0)

    def test_duplicate_opportunity_names_cannot_auto_train(self):
        q=quote(1)
        data=one_to_one_candidates(inventory([q]),[q],
                                  [opportunity(1),opportunity(2,name=opportunity(1)["opportunity_name"])],[])
        self.assertEqual(data["summary"]["structurally_one_to_one_candidates"],0)

    def test_contact_label_mismatch_holds(self):
        q=quote(1)
        o=opportunity(1)
        o["contact_display"]="김영희 KimYoungHee"
        data=one_to_one_candidates(inventory([q]),[q],[o],[])
        self.assertEqual(data["summary"]["structurally_one_to_one_candidates"],0)

    def test_existing_contact_proof_not_quote_parent_proof(self):
        q=quote(1)
        evidence=[{"opportunity_ids":[q["oppo_id"]],
                   **{flag:True for flag in (
                      "contact_detail_id_verified","contact_account_link_verified",
                      "opportunity_contact_link_verified","contact_email_verified",
                      "contact_display_name_verified")}}]
        data=one_to_one_candidates(inventory([q]),[q],[opportunity(1)],evidence)
        self.assertEqual(data["summary"]["with_independently_verified_contact_oppo"],1)
        self.assertFalse(data["candidates"][0]["native_quote_parent_independently_live_verified"])

    def test_three_round_determinism(self):
        q=quote(1)
        runs=[one_to_one_candidates(inventory([q]),[q],[opportunity(1)],[]) for _ in range(3)]
        self.assertEqual(runs[0],runs[1])
        self.assertEqual(runs[1],runs[2])


if __name__=="__main__":
    unittest.main()
