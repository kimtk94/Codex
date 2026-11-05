import unittest
from audit_one_to_one_service_patterns_private import classify_name,classify_shortlist


def record(idx,name):
    return {"quote_id":f"a0P{idx:012d}AAA",
            "oppo_id":f"006{idx:012d}AAA","oppo_name":name}


def candidate(idx):
    return {"quote_id":f"a0P{idx:012d}AAA",
            "opportunity_id":f"006{idx:012d}AAA",
            "single_product_snapshot":True,
            "snapshot_opportunity_and_contact_labels_match":True,
            "quote_name_unique_in_full_inventory":True,
            "salesforce_save_allowed":False}


class ServicePatternAuditTests(unittest.TestCase):
    def test_known_single_name_hints_only(self):
        self.assertEqual(classify_name("Korea-5-PMP-PE250-1M reads"),"NAME_HINT_ONLY_PMP")
        self.assertEqual(classify_name("Korea-3-mRNA-Seq-6Gb"),"NAME_HINT_ONLY_mRNA")
        self.assertEqual(classify_name("Korea-200-Deep DIA"),"NAME_HINT_ONLY_DIA")

    def test_no_guess_if_unknown(self):
        self.assertEqual(classify_name("Korea-5-bio-service"),"HOLD_UNCLASSIFIED_NAME")

    def test_multiple_service_tokens_hold(self):
        self.assertEqual(classify_name("Korea-5-PMP-mRNA"),"HOLD_MULTIPLE_SERVICE_HINTS")

    def test_no_substring_false_positive(self):
        self.assertEqual(classify_name("Example-PMPipeline"),"HOLD_UNCLASSIFIED_NAME")

    def test_identical_single_product_quote_not_price_approval(self):
        q=[record(1,"Korea-5-PMP-PE250")]
        s={"summary":{"structurally_one_to_one_candidates":1},"candidates":[candidate(1)]}
        out=classify_shortlist(s,q)
        self.assertEqual(out["service_label_counts"],{"NAME_HINT_ONLY_PMP":1})
        self.assertFalse(out["single_service_confirmed_from_name"])
        self.assertFalse(out["current_product_catalog_verified"])
        self.assertFalse(out["prices_verified"])
        self.assertFalse(out["salesforce_save_allowed"])

    def test_parent_id_mismatch_holds(self):
        with self.assertRaises(ValueError):
            classify_shortlist({"summary":{"structurally_one_to_one_candidates":1},
                                "candidates":[candidate(2)]},
                               [record(2,"Example-PMP")|{"oppo_id":"006000000000001AAA"}])

    def test_three_repeat_determinism(self):
        s={"summary":{"structurally_one_to_one_candidates":1},"candidates":[candidate(1)]}
        q=[record(1,"Example-mRNA")]
        runs=[classify_shortlist(s,q) for _ in range(3)]
        self.assertEqual(runs[0],runs[1])
        self.assertEqual(runs[1],runs[2])


if __name__=="__main__":
    unittest.main()
