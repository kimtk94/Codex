import unittest
from unittest.mock import MagicMock
from locator_audit import inspect, classify

class AuditTests(unittest.TestCase):
    def test_only_aggregate_counts(self):
        page=MagicMock()
        page.evaluate.return_value={"dialog_found":True,"controls":[
            {"tag":"input","required":True,"label_present":True},
            {"tag":"button","required":False,"label_present":False}]}
        result=inspect(page)
        self.assertEqual(result["control_count"],2)
        self.assertEqual(result["required_count"],1)
        self.assertEqual(result["control_types"]["input"],1)
        self.assertNotIn("controls",result)
    def test_missing_dialog(self):
        page=MagicMock()
        page.evaluate.return_value={"dialog_found":False,"controls":[]}
        self.assertFalse(inspect(page)["dialog_found"])
    def test_unknown_tags_redacted(self):
        self.assertEqual(classify("script"),"other")
if __name__=="__main__":
    unittest.main()
