"""Offline unit/integration checks: synthetic Git repos only, no GitHub API calls."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from local_ai_pr_gate import (
    MAX_FILES,
    MAX_LINES,
    actual_diff,
    allowed_path,
    evaluate,
    load_event,
)

BODY = "Task-ID: LOCAL-AI-001\nAcceptance: scope gate reports review required after valid checks."


class GatePolicyTests(unittest.TestCase):
    def test_valid_small_task_requires_human_review(self):
        result = evaluate(
            ["local_ai/reader.py", "local_ai/tests/test_reader.py"], 80, BODY, True
        )
        self.assertEqual(result["scope_check"], "PASS")
        self.assertEqual(result["review_decision"], "HUMAN_REVIEW_REQUIRED")
        self.assertFalse(result["actions_performed"]["pr_merge"])
        self.assertTrue(result["draft"])

    def test_never_approves_even_when_not_draft(self):
        result = evaluate(["local_ai/example.py"], 1, BODY, False)
        self.assertEqual(result["review_decision"], "HUMAN_REVIEW_REQUIRED")

    def test_operational_only_workflow_change_is_not_applicable(self):
        result = evaluate([".github/workflows/css-payment-sync.yml"], 3, BODY, True)
        self.assertEqual(result["scope_check"], "PASS")
        self.assertEqual(result["review_decision"], "NOT_APPLICABLE")

    def test_rejects_sensitive_or_traversal_path(self):
        for path in [
            "local_ai/../css/sfdc.py", "local_ai\\.env", ".github/workflows/deploy.yml",
            "google_drive/secrets.json", "local_ai/", "/local_ai/test.py",
        ]:
            with self.subTest(path=path):
                self.assertFalse(allowed_path(path))

    def test_flags_workflow_manual_review(self):
        result = evaluate([".github/workflows/local-ai-offline-checks.yml"], 10, BODY, True)
        self.assertEqual(result["scope_check"], "PASS")
        self.assertTrue(result["additional_workflow_review_required"])

    def test_unrelated_large_operational_pr_is_not_applicable(self):
        paths = [f"css/large_report_{i}.py" for i in range(25)]
        result = evaluate(paths, 2500, "", True)
        self.assertEqual(result["scope_check"], "PASS")
        self.assertEqual(result["review_decision"], "NOT_APPLICABLE")
        self.assertFalse(result["local_ai_change_detected"])
        self.assertEqual(result["failures"], [])

    def test_mixed_local_ai_and_operational_change_stays_blocked(self):
        result = evaluate(["local_ai/reader.py", "css/payment.py"], 30, BODY, True)
        self.assertEqual(result["scope_check"], "FAIL")
        self.assertIn("OUT_OF_SCOPE_PATH", result["failures"])

    def test_local_ai_file_without_task_metadata_stays_blocked(self):
        result = evaluate(["local_ai/a.py"], 3, "", True)
        self.assertIn("TASK_ID_MISSING", result["failures"])
        self.assertIn("ACCEPTANCE_CRITERIA_MISSING", result["failures"])

    def test_requires_task_id_and_acceptance(self):
        result = evaluate(["local_ai/a.py"], 4, "Please merge this", True)
        self.assertIn("TASK_ID_MISSING", result["failures"])
        self.assertIn("ACCEPTANCE_CRITERIA_MISSING", result["failures"])

    def test_changed_file_and_line_caps(self):
        paths = [f"local_ai/file_{i}.py" for i in range(MAX_FILES + 1)]
        result = evaluate(paths, MAX_LINES + 1, BODY, True)
        self.assertIn("TOO_MANY_FILES", result["failures"])
        self.assertIn("TOO_MANY_CHANGED_LINES", result["failures"])

    def test_duplicate_paths_cannot_pass(self):
        result = evaluate(["local_ai/a.py", "local_ai/a.py"], 2, BODY, True)
        self.assertIn("DUPLICATE_PATHS", result["failures"])

    def test_invalid_sha_rejected_before_git(self):
        with self.assertRaises(ValueError):
            actual_diff("main", "HEAD")

    def test_event_body_loading(self):
        with tempfile.TemporaryDirectory() as d:
            event = Path(d) / "event.json"
            event.write_text(json.dumps({"pull_request": {"body": BODY, "draft": True}}))
            self.assertEqual(load_event(event), (BODY, True))

    def test_actual_git_diff_counts_and_names(self):
        def git(directory, *args):
            return subprocess.check_output(
                ["git", "-C", str(directory), *args], stderr=subprocess.PIPE
            ).decode().strip()

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            path = root / "local_ai" / "example.py"
            path.parent.mkdir(parents=True)
            path.write_text("print('a')\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "-c", "user.email=ci@example.com",
                "-c", "user.name=CI", "commit", "-qm", "base")
            base = git(root, "rev-parse", "HEAD")
            path.write_text("print('b')\nprint('c')\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "-c", "user.email=ci@example.com",
                "-c", "user.name=CI", "commit", "-qm", "head")
            head = git(root, "rev-parse", "HEAD")
            # actual_diff runs in current working directory; set with patch or
            # temporarily change cwd, restoring it after the test.
            import os
            cwd = os.getcwd()
            try:
                os.chdir(root)
                paths, lines = actual_diff(base, head)
            finally:
                os.chdir(cwd)
            self.assertEqual(paths, ["local_ai/example.py"])
            self.assertEqual(lines, 3)


if __name__ == "__main__":
    unittest.main()
