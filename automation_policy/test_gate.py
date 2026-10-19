import unittest
from automation_policy.gate import evaluate

class GateTests(unittest.TestCase):
    def test_allowed_tasks(self):
        for action in ("research.analysis_qc", "research.docs_web_update", "github.code_pr", "kalman.backtest"):
            self.assertTrue(evaluate(action)["allowed"], action)

    def test_protected_tasks_fail_closed(self):
        for action in ("css.email_send", "kalman.live_order", "kalman.risk_limit_change", "database.schema_change"):
            self.assertFalse(evaluate(action, {"approved": True, "approval_token": "fake"})["allowed"], action)

    def test_unknown_denied(self):
        self.assertFalse(evaluate("execute_shell")["allowed"])

    def test_deploy_requires_all_evidence(self):
        self.assertFalse(evaluate("deployment.production", {"ci_passed": True})["allowed"])
        evidence = dict.fromkeys(("ci_passed", "security_checks_passed", "artifact_verified", "rollback_ready", "environment_allowed"), True)
        evidence.update(target="production", commit_sha="abcdef12345")
        self.assertTrue(evaluate("deployment.production", evidence)["allowed"])
        evidence["security_checks_passed"] = False
        self.assertFalse(evaluate("deployment.production", evidence)["allowed"])

if __name__ == "__main__":
    unittest.main()
