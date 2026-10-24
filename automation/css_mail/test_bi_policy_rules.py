import unittest
from automation.css_mail.bi_policy_rules import (
    canonical_institution, wgs_subtype, assert_wgs_reconciled
)

class BIPolicyTests(unittest.TestCase):
    def test_university_and_hospital(self):
        rules = {"Yonsei Univ. Hospital": "Yonsei Univ.",
                 "Yonsei University": "Yonsei Univ.",
                 "Kyungpook University": "Kyungpook Univ."}
        self.assertEqual(canonical_institution("Yonsei Univ. Hospital", rules), "Yonsei Univ.")
        self.assertEqual(canonical_institution("Yonsei University", rules), "Yonsei Univ.")
        self.assertEqual(canonical_institution("Kyungpook University", rules), "Kyungpook Univ.")
        self.assertEqual(canonical_institution("AgingLab", rules), "AgingLab")

    def test_alias_cycle(self):
        with self.assertRaises(ValueError):
            canonical_institution("A", {"A":"B", "B":"A"})

    def test_wgs_subtypes(self):
        self.assertEqual(wgs_subtype("WGS/WES", "Human WGS"), "Human")
        self.assertEqual(wgs_subtype("WGS/WES", "Microbial WGS"), "Microbial")
        self.assertEqual(wgs_subtype("WGS/WES", "Plant / Animal WGS"), "기타 (Plant/Animal)")
        self.assertEqual(wgs_subtype("WGS/WES", "WGS / Type Review"), "기타 (유형 확인 필요)")
        self.assertEqual(wgs_subtype("mRNA", "Human WGS"), "")

    def test_amount_conservation(self):
        records=[("WGS/WES","Human WGS",900),("WGS/WES","Microbial WGS",400),
                 ("WGS/WES","WGS / Type Review",300),("mRNA","mRNA-seq",100)]
        totals=assert_wgs_reconciled(records)
        self.assertEqual(sum(v[0] for v in totals.values()),3)
        self.assertEqual(sum(v[1] for v in totals.values()),1600)

if __name__ == "__main__":
    unittest.main()
