import unittest
from ops_failure_audit import classify,make_report
class FailureAuditTest(unittest.TestCase):
    def test_fail_then_success_is_candidate_only(self):
        a=[{"id":1,"event":"schedule","status":"completed","conclusion":"failure","created_at":"2026-10-25T00:00:00Z"},
           {"id":2,"event":"schedule","status":"completed","conclusion":"success","created_at":"2026-10-26T00:00:00Z"}]
        self.assertEqual("FOLLOWED_BY_SUCCESS",classify(a)[0]["state"])
        self.assertEqual("NOT_VERIFIED",make_report({"x":a})["alert_delivery"])
    def test_pr_failure_is_not_ops_incident(self):
        self.assertEqual([],classify([{"event":"pull_request","status":"completed","conclusion":"failure"}]))
    def test_unresolved(self):
        a=[{"id":1,"event":"schedule","status":"completed","conclusion":"failure","created_at":"2026-10-25"}]
        self.assertEqual("UNRESOLVED",classify(a)[0]["state"])
if __name__=="__main__": unittest.main()
