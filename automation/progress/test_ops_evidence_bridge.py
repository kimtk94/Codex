import unittest
from ops_evidence_bridge import combine
class TestBridge(unittest.TestCase):
    def test_receipt_observed_but_approval_stays_blocked(self):
        result=combine({"missing_requirements":["sheet_publish_readback","explicit_review"]},
         {"state":"OBSERVED","reason":"MATCHING_SCHEDULED_WRITE_AND_CURRENT_CELLS","run_id":123})
        self.assertEqual("OBSERVED",result["sheet_publish_readback"])
        self.assertEqual("NOT_VERIFIED",result["gate_OPS_01"])
        self.assertNotIn("sheet_publish_readback",result["missing_requirements"])
    def test_unverified_does_not_clear_gap(self):
        result=combine({"missing_requirements":["sheet_publish_readback"]},
         {"state":"NOT_CHECKED","reason":"credentials_missing"})
        self.assertEqual("NOT_OBSERVED",result["sheet_publish_readback"])
        self.assertEqual(["sheet_publish_readback"],result["missing_requirements"])
if __name__=="__main__":unittest.main()
