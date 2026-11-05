"""Synthetic-only Contact expansion progress: no customer identifiers in reports."""
import unittest
from expand_korean_contacts_private import calculate_expansion_progress

CIDS=[f"003{i:012d}AAA" for i in range(1,5)]
OIDS=[f"006{i:012d}AAA" for i in range(1,5)]
FLAGS=("contact_detail_id_verified","contact_account_link_verified",
       "opportunity_contact_link_verified","contact_email_verified",
       "contact_display_name_verified")

def person(i):
    return {"contact_id":CIDS[i],"account_id":f"001{i+1:012d}AAA",
            "display_name":"김민수 KimMinSu","contact_email":f"synthetic{i}@example.test",
            "institution":"Synthetic University","opportunity_ids":[OIDS[i]],
            **{flag:True for flag in FLAGS}}

def candidate(i):
    return {"contact_id":CIDS[i],"opportunity_id":OIDS[i]}

class ContactProgressTests(unittest.TestCase):
    def test_original_overlaps_excluded_from_new_cohort(self):
        report=calculate_expansion_progress(
            [candidate(i) for i in range(3)],
            [person(0),person(1)],
            [{"contact_id":CIDS[1],"status":"PASS_ALL_IDENTITY_CHECKS"},
             {"contact_id":CIDS[2],"status":"HOLD_CONTACT_DETAIL_DISPLAY"}])
        self.assertEqual(report["source_candidate_contacts"],3)
        self.assertEqual(report["previously_approved_candidate_overlaps"],1)
        self.assertEqual(report["new_cohort_total"],2)
        self.assertEqual(report["new_cohort_reviewed"],2)
        self.assertEqual(report["new_cohort_pass"],1)
        self.assertEqual(report["new_cohort_hold"],1)
        self.assertEqual(report["new_cohort_unreviewed"],0)
        self.assertFalse(report["salesforce_save_allowed"])
        self.assertNotIn(CIDS[1],str(report))

    def test_untested_are_not_approved(self):
        report=calculate_expansion_progress([candidate(i) for i in range(3)],
                                            [person(0)],[])
        self.assertEqual(report["new_cohort_total"],2)
        self.assertEqual(report["new_cohort_unreviewed"],2)
        self.assertEqual(report["new_cohort_reviewed"],0)

    def test_duplicate_retries_deduplicated_and_latest_hold_reason(self):
        report=calculate_expansion_progress(
            [candidate(0)],[],
            [{"contact_id":CIDS[0],"status":"HOLD_TimeoutError"},
             {"contact_id":CIDS[0],"status":"HOLD_CONTACT_EMAIL_IDENTITY"}])
        self.assertEqual(report["new_cohort_reviewed"],1)
        self.assertEqual(report["new_cohort_hold_reasons"],{"HOLD_CONTACT_EMAIL_IDENTITY":1})

    def test_conflicting_candidate_rows_fail_closed(self):
        with self.assertRaises(ValueError):
            calculate_expansion_progress([candidate(0),candidate(0)],[],[])

    def test_invalid_evidence_fails_closed(self):
        with self.assertRaises(ValueError):
            calculate_expansion_progress([],{},[])

    def test_three_identical_runs(self):
        values=[calculate_expansion_progress([candidate(0)],[],[]) for _ in range(3)]
        self.assertEqual(values[0],values[1])
        self.assertEqual(values[1],values[2])

if __name__=="__main__":
    unittest.main()
