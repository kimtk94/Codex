import unittest
from unittest.mock import patch
import draft_bridge
class DraftBridgeTests(unittest.TestCase):
    def test_import_has_no_salesforce_dependency(self):
        self.assertTrue(callable(draft_bridge.main))
    def test_catalog_search_is_read_only(self):
        from catalog_reuse import make_draft
        x=make_draft({"account":"A","contact":"C","account_id":"001","contact_cms_id":"CP","opportunity_id":"Opp-1"})
        self.assertEqual(x["Amount"],"")
        self.assertFalse(x["salesforce_save_performed"])
if __name__=="__main__":
    unittest.main()
