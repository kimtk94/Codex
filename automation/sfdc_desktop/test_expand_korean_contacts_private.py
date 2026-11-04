"""Synthetic-only tests for new Opportunity-population Contact discovery."""
import unittest
from expand_korean_contacts_private import expand_candidates,select_unverified

C1="003000000000001AAA"
C2="003000000000002AAA"
O1="006000000000001AAA"
O2="006000000000002AAA"
O3="006000000000003AAA"
O4="006000000000004AAA"


def entry(opp=O1,cid=C1,label="김민수 KimMinSu",status="UNIQUE_DISPLAY_NAME_PENDING_REAL_LINK"):
    return {"opportunity_id":opp,"candidate_contact_ids":[cid],
            "contact_display":label,"status":status}


def person(cid=C1,name="김민수 KimMinSu",email="synthetic@example.org"):
    return {"id":cid,"name":name,"cells":[email]}


class ExpandedCandidateTests(unittest.TestCase):
    def test_new_outside_180_sample(self):
        result=expand_candidates([entry()],[{"opportunity_id":O2}],[person()])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["contact_id"],C1)
        self.assertEqual(result[0]["opportunity_id"],O1)

    def test_historical_opportunity_not_rechecked(self):
        self.assertEqual(expand_candidates([entry()],[{"opportunity_id":O1}],[person()]),[])

    def test_multiple_opportunities_single_contact_not_false_multi_verified(self):
        r=expand_candidates([entry(O2),entry(O1)],[],[person()])
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]["opportunity_id"],O1)

    def test_homonym_ambiguous_row_unapproved(self):
        self.assertEqual(expand_candidates([entry(status="HOMONYM_REQUIRES_INSTITUTION_AND_ID")],[],[person()]),[])

    def test_name_mismatch_not_auto_inferred(self):
        self.assertEqual(expand_candidates([entry()],[],[person(name="김영희 KimYoungHee")]),[])

    def test_no_existing_email(self):
        self.assertEqual(expand_candidates([entry()],[],[person(email="")]),[])

    def test_conflicting_emails_held(self):
        self.assertEqual(expand_candidates([entry()],[],[person(email="first@example.org"),person(email="second@example.org")]),[])

    def test_english_only_name_held(self):
        self.assertEqual(expand_candidates([entry(label="KimMinSu")],[],[person(name="KimMinSu")]),[])

    def test_same_contact_conflicting_labels_held(self):
        self.assertEqual(expand_candidates([entry(O1,C1,"김민수 KimMinSu"),
                                            entry(O2,C1,"김영희 KimYoungHee")],
                                           [],[person()]),[])
        # A conflicting Opportunity label is a HOLD, not evidence of one safe link.

    def test_conflicting_source_name_never_silently_picks_roster_match(self):
        first=entry(O1,C1,"김민수 KimMinSu")
        second=entry(O2,C1,"김영희 KimYoungHee")
        self.assertEqual(expand_candidates([first,second],[],[person()]),[])
        self.assertEqual(expand_candidates([second,first],[],[person()]),[])

    def test_existing_verified_contacts_skipped(self):
        rows=[{"contact_id":C1},{"contact_id":C2}]
        selected=select_unverified(rows,[{"contact_id":C1}],[],0,2)
        self.assertEqual(selected,[{"contact_id":C2}])

    def test_hold_skipped_unless_explicit_retry(self):
        rows=[{"contact_id":C1},{"contact_id":C2}]
        previously=[{"contact_id":C1,"status":"HOLD_CONTACT_DETAIL_DISPLAY"}]
        self.assertEqual(select_unverified(rows,[],previously,0,2),[{"contact_id":C2}])
        self.assertEqual(len(select_unverified(rows,[],previously,0,2,True)),2)

    def test_repeat_exact_selection(self):
        source=expand_candidates([entry(O2),entry(O1)],[],[person()])
        selections=[select_unverified(source,[],[],0,5) for _ in range(3)]
        self.assertEqual(selections[0],selections[1])
        self.assertEqual(selections[1],selections[2])

    def test_zero_length_input(self):
        self.assertEqual(expand_candidates([],[],[]),[])

    def test_invalid_snapshot_type(self):
        with self.assertRaises(ValueError):
            expand_candidates({},[],[])


if __name__=="__main__":
    unittest.main()
