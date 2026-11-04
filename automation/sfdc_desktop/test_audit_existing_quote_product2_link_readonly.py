"""Synthetic-only independent native Quotation Product -> Product2 audits."""
import unittest
from audit_existing_quote_product2_link_readonly import (
    compare_snapshot_links, unique_record_links, same_record,
)

def anchors(quote_product="a0N000000000001AAA",quote="a0P000000000001AAA",
            product="01t000000000001AAA"):
    return [
        {"href":"/lightning/r/Quotation_Products__c/"+quote_product+"/view"},
        {"href":"/lightning/r/Quotation__c/"+quote+"/view"},
        {"href":"/lightning/r/Product2/"+product+"/view"},
        {"href":"/lightning/r/User/005000000000001AAA/view"},
    ]


class Product2NativeAuditTests(unittest.TestCase):
    def test_one_exact_match_each_kind(self):
        x=unique_record_links(anchors())
        self.assertEqual(set(x),{"Quotation_Products__c","Quotation__c","Product2"})
        self.assertTrue(compare_snapshot_links(anchors(),anchors()))

    def test_different_product_id_fails(self):
        self.assertFalse(compare_snapshot_links(anchors(),
                         anchors(product="01t000000000002AAA")))

    def test_different_quote_id_fails(self):
        self.assertFalse(compare_snapshot_links(anchors(),
                         anchors(quote="a0P000000000002AAA")))

    def test_missing_product2_link_fails(self):
        self.assertFalse(compare_snapshot_links(anchors(),
                         anchors()[:2]))

    def test_duplicate_product2_link_fails(self):
        extra=anchors()+[{"href":"/lightning/r/Product2/01t000000000002AAA/view"}]
        self.assertIsNone(unique_record_links(extra))
        self.assertFalse(compare_snapshot_links(anchors(),extra))

    def test_wrong_object_record_id_fails(self):
        self.assertFalse(compare_snapshot_links(anchors(),
                         anchors(quote_product="a0N000000000002AAA")))

    def test_same_native_15_18_id_accepted(self):
        self.assertTrue(same_record("01t000000000001","01t000000000001AAA"))
        self.assertFalse(same_record("01t000000000001","01t000000000002AAA"))

    def test_unrelated_navigation_links_ignored(self):
        self.assertEqual(unique_record_links(anchors()+[{"href":"/lightning/r/Account/001000000000001AAA/view"}]),
                         unique_record_links(anchors()))

    def test_ambiguous_link_is_not_reconciled_by_order(self):
        items=anchors()+[{"href":"/lightning/r/Product2/01t000000000002AAA/view"}]
        self.assertFalse(compare_snapshot_links(anchors(),items))
        self.assertFalse(compare_snapshot_links(anchors(),list(reversed(items))))

    def test_three_repeat_determinism(self):
        checks=[compare_snapshot_links(anchors(),anchors()) for _ in range(3)]
        self.assertEqual(checks,[True,True,True])


if __name__=="__main__":
    unittest.main()
