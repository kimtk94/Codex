import unittest
from gate_evaluator import evaluate

M = {"gates":{"G1":{"tasks":["A01","A02"],"required":["run_url","counts"]}}}

class TestGateEvaluator(unittest.TestCase):
    def test_pr_only_does_not_pass(self):
        self.assertEqual("NOT_VERIFIED",evaluate(M,{"A01":{"pr":"url"}})[0]["state"])
    def test_partial_one_task_not_enough(self):
        a={"gate_id":"G1","decision":"ACCEPTED","reviewer":"approved-test-reviewer",
           "reviewed_at":"2026-10-26T10:00:00Z","evidence":{"run_url":"https://example.org/1","counts":"verified"}}
        self.assertEqual("NOT_VERIFIED",evaluate(M,{"A01":a})[0]["state"])
    def test_explicit_complete_records(self):
        a={"gate_id":"G1","decision":"ACCEPTED","reviewer":"approved-test-reviewer",
           "reviewed_at":"2026-10-26T10:00:00Z","evidence":{"run_url":"https://example.org/1","counts":"verified"}}
        self.assertEqual("ACCEPTED",evaluate(M,{"A01":a,"A02":a})[0]["state"])
    def test_missing_required_evidence(self):
        a={"gate_id":"G1","decision":"ACCEPTED","reviewer":"approved-test-reviewer",
           "reviewed_at":"2026-10-26T10:00:00Z","evidence":{"run_url":"https://example.org/1"}}
        self.assertEqual("NOT_VERIFIED",evaluate(M,{"A01":a,"A02":a})[0]["state"])

if __name__=="__main__":
    unittest.main()
