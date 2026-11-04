import unittest
from verify_related_quote_native_parent import same_native,identity_result

O="006000000000001AAA"
Q="a0P000000000001AAA"

class QuoteParentNativeTests(unittest.TestCase):
    def test_unique_quote_matching_parent(self):
        r=identity_result(O,{Q},{O})
        self.assertEqual(r["status"],"QUOTE_NATIVE_PARENT_MATCH_REVIEW_COMPLETE")
        self.assertTrue(r["parent_verified"])
    def test_no_quote_anchor(self):
        self.assertEqual(identity_result(O,set(),{O})["status"],"HOLD_QUOTE_LINK_NOT_UNIQUE")
    def test_two_quote_anchors(self):
        self.assertEqual(identity_result(O,{Q,"a0P000000000002AAA"},{O})["status"],"HOLD_QUOTE_LINK_NOT_UNIQUE")
    def test_wrong_parent(self):
        self.assertEqual(identity_result(O,{Q},{"006000000000002AAA"})["status"],"HOLD_QUOTE_PARENT_ID_MISMATCH")
    def test_no_parent_link(self):
        self.assertEqual(identity_result(O,{Q},set())["status"],"HOLD_QUOTE_PARENT_NOT_UNIQUE")
    def test_15_vs_18_variant(self):
        self.assertTrue(same_native(O[:15],O))
        self.assertFalse(same_native(O[:15],"006000000000002AAA"))
    def test_unrelated_object_id(self):
        self.assertFalse(same_native(Q,O))
    def test_three_repeat(self):
        self.assertEqual(len({identity_result(O,{Q},{O})["status"] for _ in range(3)}),1)

if __name__=="__main__":
    unittest.main()
