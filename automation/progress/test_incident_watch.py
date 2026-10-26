import unittest
from incident_watch import incidents_for_workflow,issue_title
class TestIncidentWatch(unittest.TestCase):
    def test_detect_unresolved_schedule(self):
        x=incidents_for_workflow([{"id":123,"event":"schedule","status":"completed","conclusion":"failure","created_at":"2026-10-25T00:00:00Z"}],"test.yml")
        self.assertEqual(123,x[0]["run_id"])
        self.assertIn("123",issue_title(x[0]))
    def test_followed_by_success_not_alerted(self):
        runs=[{"id":123,"event":"schedule","status":"completed","conclusion":"failure","created_at":"2026-10-25T00:00:00Z"},
              {"id":124,"event":"schedule","status":"completed","conclusion":"success","created_at":"2026-10-26T00:00:00Z"}]
        self.assertEqual([],incidents_for_workflow(runs,"test.yml"))
    def test_pr_failure_ignored(self):
        self.assertEqual([],incidents_for_workflow([{"id":1,"event":"pull_request","status":"completed","conclusion":"failure"}],"test.yml"))
if __name__=="__main__":unittest.main()
