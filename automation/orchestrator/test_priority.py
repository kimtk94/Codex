"""Offline tests for GitHub CI next-task prioritizer: no HTTP, credentials or CRM."""
import json
from pathlib import Path
import tempfile
import unittest

import priority


def item(run_id, status="completed", conclusion="success", created_at="2026-11-16T12:00:00Z",
         branch="main", event="schedule"):
    return {
        "id": run_id, "head_branch": branch, "event": event,
        "status": status, "conclusion": conclusion,
        "created_at": created_at,
        "html_url": "https://malicious.invalid/never-trust-returned-link",
    }


def payload(*runs):
    return {"workflow_runs": list(runs)}


class PriorityTests(unittest.TestCase):
    def setUp(self):
        self.policy = priority.load_policy()

    def test_has_all_nine_domains_and_actual_repo_workflows(self):
        self.assertEqual(9, len(self.policy["domains"]))
        self.assertEqual(9, len({x["workflow"] for x in self.policy["domains"]}))
        for x in self.policy["domains"]:
            self.assertTrue(priority.workflow_url(priority.EXPECTED_REPO, x["workflow"]).endswith(
                x["workflow"] + "/runs?branch=main&per_page=5"))

    def test_failed_latest_main_run_takes_precedence_over_previous_success(self):
        result = priority.run_signal(payload(
            item(1, created_at="2026-11-15T12:00:00Z"),
            item(3, status="completed", conclusion="failure", created_at="2026-11-16T12:00:00Z"),
            item(99, status="completed", conclusion="success", branch="test",
                 created_at="2026-11-16T13:00:00Z")))
        self.assertEqual("CI_FAILED", result["signal"])
        self.assertEqual(3, result["run_id"])
        self.assertEqual("https://github.com/kimtk94/Codex/actions/runs/3", result["run_url"])

    def test_in_progress_is_not_previous_success(self):
        result = priority.run_signal(payload(
            item(1, status="completed", conclusion="success", created_at="2026-11-15T12:00:00Z"),
            item(2, status="in_progress", conclusion=None, created_at="2026-11-16T12:00:00Z")))
        self.assertEqual("CI_PENDING", result["signal"])

    def test_pr_runs_and_other_branches_do_not_count(self):
        result = priority.run_signal(payload(
            item(1, branch="feature", event="push"),
            item(2, branch="main", event="pull_request")))
        self.assertEqual("CI_NO_MAIN_RUN", result["signal"])
        self.assertIsNone(result["run_url"])

    def test_success_never_certifies_business_freshness(self):
        report = priority.build_priority(self.policy, fetch=lambda url, token: payload(item(1)))
        self.assertEqual("NOT_VERIFIED", report["business_source_sink_verification"])
        self.assertFalse(report["auto_execute_business_writes"])
        self.assertFalse(report["auto_merge_pr"])
        self.assertTrue(all(x["signal"] == "CI_SUCCESS_UNVERIFIED" for x in report["queue"]))
        self.assertTrue(all(not x["business_source_checked"] and not x["business_sink_checked"]
                            for x in report["queue"]))

    def test_actual_failure_ranked_over_missing_runs_and_success(self):
        names = [x["workflow"] for x in self.policy["domains"]]
        def fetch(url, token):
            if names[2] in url:
                return payload(item(30, conclusion="failure"))
            if names[1] in url:
                return payload()
            return payload(item(8))
        report = priority.build_priority(self.policy, fetch=fetch)
        self.assertEqual("quote", report["next_review"]["domain"])
        self.assertEqual("INSPECT_FAILURE_LOGS_READ_ONLY", report["next_review"]["next_safe_action"])
        self.assertEqual("lead", report["queue"][1]["domain"])

    def test_api_failure_is_unavailable_not_no_data(self):
        def fetch(url, token):
            raise OSError("connection refused")
        report = priority.build_priority(self.policy, fetch=fetch)
        self.assertEqual(9, report["unavailable_workflow_count"])
        self.assertEqual("CI_API_UNAVAILABLE", report["next_review"]["signal"])
        self.assertNotIn("connection refused", json.dumps(report))
        self.assertIn("RESTORE_GITHUB_RUN_VISIBILITY", priority.summary(report))

    def test_unsupported_status_is_unknown_and_fail_closed(self):
        result = priority.run_signal(payload(item(1, status="completed", conclusion="not_valid")))
        self.assertEqual("CI_UNKNOWN", result["signal"])
        with self.assertRaises(ValueError):
            priority.run_signal(payload(item(1, created_at="missing")))

    def test_repo_and_workflow_input_are_restricted(self):
        with self.assertRaises(ValueError):
            priority.workflow_url("outsider/repo", "audit.yml")
        with self.assertRaises(ValueError):
            priority.workflow_url(priority.EXPECTED_REPO, "../private.yml")
        with self.assertRaises(ValueError):
            priority.build_priority(self.policy, repo="outsider/repo")

    def test_policy_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = json.loads(priority.POLICY_PATH.read_text())
            source["domains"][0]["workflow"] = "../danger.yml"
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(source))
            with self.assertRaises(ValueError):
                priority.load_policy(path)
            source["domains"][0]["workflow"] = source["domains"][1]["workflow"]
            path.write_text(json.dumps(source))
            with self.assertRaises(ValueError):
                priority.load_policy(path)


if __name__ == "__main__":
    unittest.main()
