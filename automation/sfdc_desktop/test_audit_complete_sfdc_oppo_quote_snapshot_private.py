"""Synthetic-only complete Quote snapshot reconciliation regressions."""
import unittest

from audit_complete_sfdc_oppo_quote_snapshot_private import summary


def opp(i):
    return {"opportunity_id":f"006{i:012d}AAA",
            "opportunity_name":f"Korea-Example-{i}-PMP-PE250-1M reads",
            "institution_hint":"Example University",
            "contact_display":"김민수 KimMinSu"}


def quote(i,parent=1,state="Ready to send"):
    return {"quote_id":f"a0P{i:012d}AAA",
            "oppo_id":f"006{parent:012d}AAA",
            "oppo_name":f"Korea-Example-{parent}-PMP-PE250-1M reads",
            "quote_name":f"Korea-Example-{parent}-PMP-PE250-1M reads-AMEA20260001",
            "quote_status":state,
            "contact_display":"김민수 KimMinSu"}


def inventory(ids,complete=True,quotes=None):
    known={q["quote_id"]:q for q in (quotes or [])}
    rows=[]
    for i in ids:
        ident=f"a0P{i:012d}AAA"
        q=known.get(ident,quote(i))
        cells=[""]*16
        cells[2]=q["quote_name"]
        cells[4]=q["oppo_name"]
        cells[5]=q["quote_status"]
        rows.append({"id":ident,"cells":cells})
    return {"fully_enumerated":complete,"limit_reached":False,"rows":rows}


class CompleteSnapshotTests(unittest.TestCase):
    def test_quote_subset_classified_without_approving_save(self):
        x=summary(inventory([1,2,3],quotes=[quote(1),quote(2)]),[quote(1),quote(2)],[opp(1)])
        self.assertEqual(x["full_quotation_count"],3)
        self.assertEqual(x["one_product_manifest_count"],2)
        self.assertEqual(x["non_one_product_or_unclassified_quote_count"],1)
        self.assertEqual(x["unique_opportunity_refs_in_single_product_quote_manifest"],1)
        self.assertEqual(x["opportunity_refs_with_multiple_quotes"],1)
        self.assertEqual(x["quotes_approved_for_automatic_save"],0)
        self.assertFalse(x["native_parent_link_independently_verified_for_all"])

    def test_external_opportunity_is_not_verified(self):
        x=summary(inventory([1],quotes=[quote(1,99)]),[quote(1,99)],[opp(1)])
        self.assertEqual(x["opportunity_relation_counts"]["parent_not_in_in_scope_opportunity_snapshot"],1)

    def test_other_quote_status_and_name_candidate_not_native_link(self):
        x=summary(inventory([1,2]),[quote(1)],[opp(1),opp(2)])
        self.assertEqual(x["non_one_product_or_unclassified_quote_count"],1)
        self.assertEqual(x["other_quote_opportunity_name_lookup"]["unique_name_only_not_native_id"],1)
        self.assertFalse(x["other_quote_native_parent_ids_verified"])

    def test_layout_drift_blocks_other_quote_classification(self):
        a=inventory([1])
        a["rows"][0]["cells"][5]="Changed status"
        with self.assertRaises(ValueError):
            summary(a,[quote(1)],[opp(1)])

    def test_duplicate_full_quote_fails(self):
        with self.assertRaises(ValueError):
            summary(inventory([1,1]),[quote(1)],[opp(1)])

    def test_invalid_subset_fails(self):
        with self.assertRaises(ValueError):
            summary(inventory([1]),[quote(2)],[opp(1)])

    def test_incomplete_full_inventory_fails(self):
        with self.assertRaises(ValueError):
            summary(inventory([1],complete=False),[quote(1)],[opp(1)])

    def test_duplicate_learned_quote_fails(self):
        with self.assertRaises(ValueError):
            summary(inventory([1]),[quote(1),quote(1)],[opp(1)])

    def test_duplicate_opportunity_fails(self):
        with self.assertRaises(ValueError):
            summary(inventory([1]),[quote(1)],[opp(1),opp(1)])

    def test_three_repeat_deterministic(self):
        runs=[summary(inventory([1]),[quote(1)],[opp(1)]) for _ in range(3)]
        self.assertEqual(runs[0],runs[1])
        self.assertEqual(runs[1],runs[2])

    def test_pe250_requires_unit_review_and_no_price_approval(self):
        x=summary(inventory([1]),[quote(1)],[opp(1)])
        self.assertEqual(x["case_unit_policy_counts"]["explicit_pe250"],1)
        self.assertFalse(x["current_product2_and_pricebook_verified_for_all"])


if __name__=="__main__":
    unittest.main()
