import unittest
from incident_watch import plan_issues,issue_title,incidents_for_workflow
class IncidentDryRunTests(unittest.TestCase):
    def test_deduplication(self):
        item={"workflow":"w.yml","run_id":42,"recovery_run_id":None}
        self.assertEqual(1,len(plan_issues([item,item],[])))
        self.assertEqual([],plan_issues([item],[issue_title(item)]))
    def test_failure_recovery_pr_ignored(self):
        failed={"id":5,"event":"schedule","status":"completed","conclusion":"failure","created_at":"2026-10-25T00:00:00Z"}
        ok={"id":6,"event":"schedule","status":"completed","conclusion":"success","created_at":"2026-10-26T00:00:00Z"}
        self.assertEqual(1,len(incidents_for_workflow([failed],"w.yml")))
        self.assertEqual([],incidents_for_workflow([failed,ok],"w.yml"))
if __name__=="__main__":unittest.main()
