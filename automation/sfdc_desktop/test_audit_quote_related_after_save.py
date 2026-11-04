import unittest
from audit_quote_related_after_save import classify_related_text,target_from_private_source

class RelatedQuoteReadOnlyTests(unittest.TestCase):
    def test_zero_not_create_permission(self):
        a=classify_related_text("Quotation\n(0)\nNew")
        self.assertEqual(a["related_quote_count"],0)
        self.assertFalse(a["create_allowed"])
    def test_one_quote_requires_independent_identity(self):
        a=classify_related_text("Quotation (1)")
        self.assertEqual(a["related_quote_count"],1)
        self.assertEqual(a["status"],"RELATED_QUOTES_PRESENT_VERIFY_INDEPENDENT_IDENTITIES")
    def test_conflicting_counts_hold(self):
        a=classify_related_text("Quotation (0)\nQuotation (1)")
        self.assertIsNone(a["related_quote_count"])
    def test_absent_section_hold(self):
        self.assertIsNone(classify_related_text("No quote section")["related_quote_count"])
    def test_target_requires_save_evidence(self):
        a={"new_opportunity_record_id":"006000000000001AAA","opportunity_save_clicked":True}
        self.assertEqual(target_from_private_source(a),"006000000000001AAA")
        a["opportunity_save_clicked"]=False
        with self.assertRaises(ValueError): target_from_private_source(a)
    def test_wrong_id_hold(self):
        with self.assertRaises(ValueError): target_from_private_source(
            {"new_opportunity_record_id":"not-an-oppo","opportunity_save_clicked":True})
    def test_repeat_deterministic_no_create(self):
        results=[classify_related_text("Quotation (0)") for _ in range(3)]
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[1],results[2])
        self.assertFalse(results[0]["create_allowed"])

if __name__=="__main__":
    unittest.main()
