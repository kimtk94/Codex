import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("css_preview_release_readonly_monitor.py")
spec = importlib.util.spec_from_file_location("css_preview_release_readonly_monitor", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SHA = "a" * 40
HEADER = ["Area", "Check", "Result", "Gate", "Evidence KST", "Observed",
          "Next action", "Checked KST"]


def fixtures():
    pr = {"number": 487, "state": "open", "head": {"sha": SHA}}
    project = {"ssoProtection": {"enabled": True,
                                 "deploymentType": "all_except_custom_domains"}}
    deployments = {"deployments": [
        {"target": None, "state": "READY", "url": "css-preview-test.vercel.app",
         "created": 10, "meta": {"githubCommitSha": SHA}},
        {"target": "production", "state": "READY", "url": "css-production.vercel.app",
         "created": 100, "meta": {"githubCommitSha": SHA}}
    ]}
    ledger = {"values": [HEADER] + [
        ["Release", c, "BLOCK", "RELEASE", "", "", "", ""]
        for c in mod.RELEASE]}
    return pr, project, deployments, ledger


class TestPreviewReleaseMonitor(unittest.TestCase):
    def test_ready_preview_is_not_approval(self):
        out = mod.evaluate(*fixtures())
        self.assertEqual(out["state"], "READY_FOR_OWNER_OAUTH_E2E")
        self.assertTrue(out["exact_sha_preview_ready"])
        self.assertEqual(out["pr_sha_prefix"], SHA[:12])
        self.assertEqual(out["acceptance_release_states"],
                         dict.fromkeys(mod.RELEASE, "BLOCK"))
        self.assertFalse(out["production_approval"])
        self.assertFalse(out["production_deploy"])
        self.assertEqual(out["owner_authenticated_browser_e2e"],
                         "NOT_VERIFIED_BY_THIS_AUDIT")
        self.assertEqual(out["preview_url"], "https://css-preview-test.vercel.app")

    def test_stale_preview_sha_blocks(self):
        args = fixtures()
        args[2]["deployments"][0]["meta"]["githubCommitSha"] = "b" * 40
        out = mod.evaluate(*args)
        self.assertEqual(out["state"], "BLOCK_READINESS")
        self.assertFalse(out["exact_sha_preview_ready"])

    def test_production_must_never_satisfy_preview_requirement(self):
        args = fixtures()
        args[2]["deployments"] = [args[2]["deployments"][1]]
        self.assertFalse(mod.evaluate(*args)["exact_sha_preview_ready"])

    def test_unprotected_deployment_blocks(self):
        args = fixtures()
        args[1]["ssoProtection"]["enabled"] = False
        self.assertEqual(mod.evaluate(*args)["state"], "BLOCK_READINESS")

    def test_missing_or_duplicate_ledger_release_rows_block(self):
        args = fixtures()
        args[3]["values"].pop()
        self.assertFalse(mod.evaluate(*args)["acceptance_ledger_schema_valid"])
        args = fixtures()
        args[3]["values"].append(args[3]["values"][1].copy())
        self.assertFalse(mod.evaluate(*args)["acceptance_ledger_schema_valid"])

    def test_wrong_pr_state_or_malicious_host_blocks(self):
        args = fixtures()
        args[0]["state"] = "closed"
        self.assertEqual(mod.evaluate(*args)["state"], "BLOCK_READINESS")
        args = fixtures()
        args[2]["deployments"][0]["url"] = "css-preview-test.vercel.app/steal"
        out = mod.evaluate(*args)
        self.assertEqual(out["state"], "BLOCK_READINESS")
        self.assertEqual(out["preview_url"], "")

    def test_release_ledger_pass_never_authorizes_production(self):
        args = fixtures()
        for row in args[3]["values"][1:]:
            row[2] = "PASS"
        out = mod.evaluate(*args)
        self.assertFalse(out["production_approval"])
        self.assertEqual(out["owner_authenticated_browser_e2e"],
                         "NOT_VERIFIED_BY_THIS_AUDIT")


if __name__ == "__main__":
    unittest.main()
