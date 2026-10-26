import unittest
from ops_evidence import assess
class OpsEvidenceTest(unittest.TestCase):
    def test_green_pr_does_not_pass_schedule(self):
        x=assess({"progress_audit":[{"event":"pull_request","conclusion":"success","id":1}]},{})
        self.assertEqual("NOT_VERIFIED",x["gate_OPS_01"])
        self.assertTrue(x["workflow_checks"]["progress_audit"]["pr_ci_success"])
        self.assertFalse(x["workflow_checks"]["progress_audit"]["three_scheduled_successes"])
    def test_three_runs_without_sheet_or_incident_remain_unverified(self):
        records={k:[{"id":i,"event":"schedule","conclusion":"success"} for i in (1,2,3)] for k in ("progress_audit","evidence_publisher","gate_gap_sync")}
        x=assess(records,{"last_checked_kst":"","evidence_url":""})
        self.assertEqual("NOT_VERIFIED",x["gate_OPS_01"])
        self.assertIn("failure_injection",x["missing_requirements"])
if __name__=="__main__": unittest.main()
