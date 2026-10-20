import unittest
from automation_policy.ckd_next_action import decide
class TestCKDNextAction(unittest.TestCase):
 def test_no_evidence_blocks(self): self.assertEqual(decide("success")["state"],"BLOCKED")
 def test_failure_blocks(self): self.assertFalse(decide("failure")["auto_execute"])
 def test_verified_report_auto_publish(self):
  s={"status":"CROSS_STAGE_QC_PASS","genes":9,"scientific_recomputation":False}
  self.assertTrue(decide("success",s)["auto_execute"])
  self.assertFalse(decide("success",s,published=True)["auto_execute"])
