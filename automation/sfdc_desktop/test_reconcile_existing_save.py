"""Never retry a Save based only on an ambiguous browser result."""
import unittest
from reconcile_existing_save import reconcile_existing_save

def evidence():
    return {"opportunity_save_clicked": True,
            "opportunity_native_id_verified": True,
            "quote_save_clicked": True,
            "quote_native_id_verified": False,
            "quote_parent_link_verified": False,
            "matching_related_quote_count": None,
            "duplicate_search_complete": False}

class ReconciliationTests(unittest.TestCase):
    def test_prior_save_without_duplicate_check(self):
        self.assertEqual(reconcile_existing_save(evidence())["status"],"HOLD_DUPLICATE_SEARCH_REQUIRED")
    def test_quote_save_ambiguous_blocks_retry(self):
        d=evidence()
        d["duplicate_search_complete"]=True
        self.assertEqual(reconcile_existing_save(d)["status"],"HOLD_QUOTE_SAVE_READBACK_NEVER_RETRY")
    def test_three_repeat_no_create(self):
        for _ in range(3):
            self.assertFalse(reconcile_existing_save(evidence())["create_allowed"])
    def test_existing_quote_verified_does_not_create_second(self):
        d=evidence()
        d.update(duplicate_search_complete=True,quote_native_id_verified=True,
                 quote_parent_link_verified=True,matching_related_quote_count=1)
        self.assertEqual(reconcile_existing_save(d)["status"],"EXISTING_QUOTE_VERIFIED_NO_CREATE")
        self.assertFalse(reconcile_existing_save(d)["create_allowed"])
    def test_wrong_related_parent(self):
        d=evidence()
        d.update(duplicate_search_complete=True,quote_native_id_verified=True,
                 matching_related_quote_count=1)
        self.assertEqual(reconcile_existing_save(d)["status"],"HOLD_QUOTE_PARENT_LINK_MISMATCH")
    def test_duplicate_child(self):
        d=evidence()
        d.update(duplicate_search_complete=True,quote_native_id_verified=True,
                 matching_related_quote_count=2)
        self.assertEqual(reconcile_existing_save(d)["status"],"HOLD_DUPLICATE_QUOTES")
    def test_unreadable_list(self):
        d=evidence()
        d.update(duplicate_search_complete=True,quote_native_id_verified=True)
        self.assertEqual(reconcile_existing_save(d)["status"],"HOLD_RELATED_LIST_UNREADABLE")
    def test_missing_evidence(self):
        self.assertFalse(reconcile_existing_save({})["create_allowed"])
    def test_integer_boolean_confusion(self):
        d=evidence()
        d["quote_save_clicked"]=1
        self.assertEqual(reconcile_existing_save(d)["status"],"HOLD_INVALID_EVIDENCE")
    def test_invalid_count(self):
        d=evidence()
        d["matching_related_quote_count"]=-1
        self.assertEqual(reconcile_existing_save(d)["status"],"HOLD_INVALID_EVIDENCE")

if __name__=="__main__":
    unittest.main()
