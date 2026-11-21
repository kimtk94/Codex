"""Synthetic offline checks for reviewed Kalman runtime hotfix proposal."""
import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.kalman import prepare_runtime_hotfix_pr as helper


class HotfixProposalSafetyTests(unittest.TestCase):
    def good_env(self):
        return {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_ACTOR": "kimtk94",
            "HOTFIX_PR_APPROVAL": helper.APPROVAL_PHRASE,
            "GITHUB_RUN_ID": "44812345678",
        }

    def test_proposal_requires_manual_authorization(self):
        for key, value in (
            ("GITHUB_EVENT_NAME", "push"),
            ("GITHUB_REF", "refs/heads/fake"),
            ("GITHUB_ACTOR", "untrusted"),
            ("HOTFIX_PR_APPROVAL", "YES"),
            ("GITHUB_RUN_ID", "bad;branch"),
        ):
            env = self.good_env()
            env[key] = value
            with self.subTest(key=key), self.assertRaises(PermissionError):
                helper.authorize_proposal(env)
        self.assertEqual(
            helper.authorize_proposal(self.good_env()),
            "automation/kalman-hotfix-pr-44812345678",
        )

    def test_non_hotfix_paths_blocked(self):
        helper.verify_changed_paths(list(helper.ALLOWED_FILES))
        for bad in ("README.md", ".github/workflows/fake.yml", "automation/css/sfdc.py"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                helper.verify_changed_paths([helper.ALLOWED_FILES[0], bad])
        with self.assertRaises(ValueError):
            helper.verify_changed_paths([helper.ALLOWED_FILES[0]] * 2)

    def test_draft_pr_has_never_main_push(self):
        calls = []

        def simulated_run(*args, **kwargs):
            calls.append(args)
            return "https://github.com/kimtk94/Codex/pull/000"

        with tempfile.TemporaryDirectory() as td:
            preview = {"changed_paths": [helper.ALLOWED_FILES[0]]}
            with patch.object(helper, "run", side_effect=simulated_run):
                branch = helper.propose(Path(td), preview, self.good_env())
        self.assertEqual(branch, "automation/kalman-hotfix-pr-44812345678")
        pushes = [cmd for cmd in calls if cmd[:2] == ("git", "push")]
        self.assertEqual(pushes, [
            ("git", "push", "origin", "HEAD:refs/heads/automation/kalman-hotfix-pr-44812345678")
        ])
        self.assertNotIn(("git", "push", "origin", "HEAD:main"), calls)
        self.assertTrue(any(cmd[:3] == ("gh", "pr", "create") and "--draft" in cmd for cmd in calls))

    def test_no_changes_does_not_push_or_create_pr(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(helper, "run", side_effect=AssertionError("unexpected write")):
                self.assertEqual(helper.propose(Path(td), {"changed_paths": []}, self.good_env()), "NO_CHANGE")

    def test_prepare_validates_manifest_and_writes_review_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / helper.ALLOWED_FILES[0]).parent.mkdir(parents=True)
            (root / helper.ALLOWED_FILES[1]).parent.mkdir(parents=True, exist_ok=True)
            app = f"/* {helper.MARKER} */\nconsole.log('syntax ok');\n"
            manifest = root / helper.ALLOWED_FILES[0]
            manifest.write_text(json.dumps({
                "file": "app.js",
                "data_b64": base64.b64encode(app.encode()).decode(),
            }) + "\n", encoding="utf-8")
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            report_file = root / helper.ALLOWED_FILES[1]
            report_file.write_text(json.dumps({
                "source_manifest_sha256": digest,
                "runtime_hotfix_manifest_only": True,
            }), encoding="utf-8")

            def fake_run(*args, **kwargs):
                if args[:3] == ("git", "status", "--porcelain"):
                    return ""
                if args[:3] == ("git", "diff", "--name-only"):
                    return "\n".join(helper.ALLOWED_FILES)
                if args[:3] == ("git", "diff", "--binary"):
                    return "fake patch"
                return ""

            out = root / "evidence"
            with patch.object(helper, "run", side_effect=fake_run):
                result = helper.prepare(root, out)
            self.assertEqual(result["decision"], "HUMAN_REVIEW_REQUIRED")
            self.assertFalse(result["pr_created"])
            self.assertFalse(result["direct_push_main"])
            self.assertTrue((out / "hotfix-preview.json").exists())
            self.assertIn("fake patch", (out / "kalman-runtime-hotfix.patch").read_text())
            self.assertEqual(json.loads((out / "hotfix-preview.json").read_text())["manifest_sha256"], digest)


if __name__ == "__main__":
    unittest.main()
