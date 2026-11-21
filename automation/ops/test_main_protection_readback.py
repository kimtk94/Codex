import unittest
from automation.ops.main_protection_readback import evaluate, matches_default_branch

BASE = "/repos/kimtk94/Codex"


def sample(protected=True, good=True, bypass=False, active=True):
    return {
        BASE: {"default_branch": "main"},
        BASE + "/branches/main": {"protected": protected, "commit": {"sha": "abc"}},
        BASE + "/rulesets?includes_parents=true": [
            {"id": 123, "target": "branch", "enforcement": "active" if active else "evaluate"}
        ],
        BASE + "/rulesets/123": {
            "id": 123,
            "target": "branch",
            "enforcement": "active" if active else "evaluate",
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
            "bypass_actors": [{"actor_id": 100}] if bypass else [],
        },
        BASE + "/rules/branches/main": [
            {"ruleset_id": 123, "type": "pull_request"},
            {"ruleset_id": 123, "type": "deletion"},
            {"ruleset_id": 123, "type": "non_fast_forward"},
            {"ruleset_id": 123, "type": "required_status_checks",
             "parameters": {"required_status_checks": [{"context": "main-write-guard" if good else "some-other-check"}]}},
        ],
    }


class MainProtectionReadbackTests(unittest.TestCase):
    def check(self, data):
        def get(path):
            if path not in data:
                raise AssertionError("unexpected read endpoint " + path)
            return data[path]
        return evaluate(get)

    def test_initial_unprotected_is_waiting_admin(self):
        x = sample(protected=False)
        x[BASE + "/rulesets?includes_parents=true"] = []
        result = self.check(x)
        self.assertEqual(result["status"], "WAITING_ADMIN")
        self.assertFalse(result["branch_protected"])

    def test_effective_protection_requires_all_controls(self):
        result = self.check(sample())
        self.assertEqual(result["status"], "PROTECTION_VERIFIED")
        self.assertTrue(result["required_check_present"])
        self.assertFalse(result["missing"])

    def test_missing_named_status_check_does_not_pass(self):
        result = self.check(sample(good=False))
        self.assertEqual(result["status"], "CONFIG_INCOMPLETE")
        self.assertIn("required_status_check:main-write-guard", result["missing"])

    def test_bypass_actor_blocks_certification(self):
        result = self.check(sample(bypass=True))
        self.assertEqual(result["status"], "CONFIG_INCOMPLETE")
        self.assertIn("bypass_actor_review", result["missing"])

    def test_evaluate_only_not_effective(self):
        result = self.check(sample(active=False))
        self.assertEqual(result["status"], "RULESET_NOT_EFFECTIVE")

    def test_branch_flag_must_be_protected(self):
        result = self.check(sample(protected=False))
        self.assertEqual(result["status"], "RULESET_NOT_EFFECTIVE")

    def test_explicit_exclusion_blocks_matching(self):
        x = sample()
        x[BASE + "/rulesets/123"]["conditions"]["ref_name"]["exclude"] = ["refs/heads/main"]
        self.assertEqual(self.check(x)["status"], "RULESET_NOT_EFFECTIVE")

    def test_missing_deletion_rule_not_certified(self):
        x = sample()
        x[BASE + "/rules/branches/main"] = [
            y for y in x[BASE + "/rules/branches/main"] if y["type"] != "deletion"
        ]
        self.assertIn("deletion", self.check(x)["missing"])

    def test_default_branch_mismatch_fails_closed(self):
        x = sample()
        x[BASE]["default_branch"] = "develop"
        with self.assertRaises(ValueError):
            self.check(x)

    def test_invalid_source_data_fails_closed(self):
        x = sample()
        x[BASE + "/rulesets?includes_parents=true"] = {}
        with self.assertRaises(ValueError):
            self.check(x)

    def test_branch_rule_matcher(self):
        self.assertTrue(matches_default_branch(sample()[BASE + "/rulesets/123"]))
        self.assertFalse(matches_default_branch({
            "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/dev"], "exclude": []}}
        }))


if __name__ == "__main__":
    unittest.main()
