import unittest
from automation_policy.plan import Step, ready, validate

class PlanTests(unittest.TestCase):
    def setUp(self):
        self.steps = [
            Step("qc", "research.analysis_qc"),
            Step("docs", "research.docs_web_update", ("qc",)),
            Step("backtest", "kalman.backtest", ("qc",)),
        ]

    def test_topological_order(self):
        self.assertEqual(validate(self.steps), ["qc", "docs", "backtest"])

    def test_unlocked_by_verified_completion(self):
        self.assertEqual(ready(self.steps, set()), ["qc"])
        self.assertEqual(ready(self.steps, {"qc"}), ["docs", "backtest"])

    def test_protected_effect_rejected(self):
        with self.assertRaisesRegex(ValueError, "action_not_allowed"):
            validate([Step("trade", "kalman.live_order")])

    def test_cycle_and_missing_dependencies(self):
        with self.assertRaisesRegex(ValueError, "dependency_cycle"):
            validate([Step("a", "research.analysis_qc", ("b",)), Step("b", "research.analysis_qc", ("a",))])
        with self.assertRaisesRegex(ValueError, "unknown_dependency"):
            validate([Step("a", "research.analysis_qc", ("missing",))])

    def test_failure_blocks_dependents(self):
        self.assertEqual(ready(self.steps, set(), {"qc"}), [])

if __name__ == "__main__":
    unittest.main()
