"""Aggregate synthetic Opportunity/Contact linkage. No real customer data."""
import unittest
from audit_all_opportunity_contact_snapshot_private import summarize_opportunities


def entry(index, contacts):
    return {"opportunity_id":f"006{index:012d}AAA",
            "opportunity_name":"Synthetic University-PMP",
            "institution_hint":"Synthetic University",
            "status":("NAME_NOT_FOUND" if not contacts else
                      "HOMONYM_REQUIRES_INSTITUTION_AND_ID" if len(contacts)>1
                      else "UNIQUE_DISPLAY_NAME_PENDING_REAL_LINK"),
            "candidate_contact_ids":contacts}

CID="003000000000001AAA"


def approved():
    return {"name":"김민수","institution":"Synthetic University",
            "contact_id":CID,"account_id":"001000000000001AAA",
            "opportunity_id":"006000000000001AAA",
            "display_name":"김민수 KimMinSu",
            "contact_email":"synthetic@example.org",
            "contact_detail_id_verified":True,
            "contact_account_link_verified":True,
            "opportunity_contact_link_verified":True,
            "contact_email_verified":True,
            "contact_display_name_verified":True}


class WholeOpportunityAuditTests(unittest.TestCase):
    def test_unique_homonym_and_missing_separated(self):
        sample=[entry(1,[CID]),entry(2,["003000000000002AAA",CID]),entry(3,[])]
        x=summarize_opportunities(sample,[approved()])
        self.assertEqual(x["opportunity_inventory_count"],3)
        self.assertEqual(x["candidate_id_multiplicity"],{0:1,1:1,2:1})
        self.assertEqual(x["approved_native_opportunity_ids_in_manifest"],1)
        self.assertEqual(x["unapproved_opportunity_rows"],2)
        self.assertFalse(x["salesforce_save_allowed"])

    def test_account_candidate_mismatch_reported_not_approved(self):
        x=summarize_opportunities([entry(1,["003000000000002AAA"])],[approved()])
        self.assertEqual(x["approved_native_opportunity_ids_in_manifest"],0)
        self.assertEqual(x["independently_approved_opportunity_id_candidate_conflicts"],1)

    def test_duplicate_opportunity_fails(self):
        with self.assertRaises(ValueError):
            summarize_opportunities([entry(1,[]),entry(1,[])],[])

    def test_invalid_contact_ids_fail(self):
        with self.assertRaises(ValueError):
            summarize_opportunities([entry(1,["FAKE"])],[])

    def test_excluded_account_fails(self):
        row=entry(1,[])
        row["institution_hint"]="KAIST"
        with self.assertRaises(ValueError):
            summarize_opportunities([row],[])

    def test_untested_without_evidence_not_auto_approved(self):
        x=summarize_opportunities([entry(1,[CID])],[])
        self.assertEqual(x["approved_native_opportunity_ids_in_manifest"],0)
        self.assertEqual(x["unapproved_opportunity_rows"],1)

    def test_three_repeat(self):
        r=[summarize_opportunities([entry(1,[CID])],[approved()]) for _ in range(3)]
        self.assertEqual(r[0],r[1])
        self.assertEqual(r[1],r[2])


if __name__=="__main__":
    unittest.main()
