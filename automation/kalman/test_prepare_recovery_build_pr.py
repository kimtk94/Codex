import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.kalman import prepare_recovery_build_pr as helper


def good_env():
    return {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_ACTOR": "kimtk94",
        "LEGACY_BUILD_APPROVAL": helper.APPROVAL,
        "GITHUB_RUN_ID": "44900123456",
    }


class LegacyBuildSafetyTests(unittest.TestCase):
    def test_all_three_versions_and_restricted_outputs(self):
        for version in ("7420", "7421", "7422"):
            with self.subTest(version=version):
                files = helper.files_for(version)
                self.assertEqual(len(files), 3)
                self.assertTrue(all(f"v7.4.{int(version[-2:])}" in x for x in files))
                helper.check_changed(version, files)
                with self.assertRaises(ValueError):
                    helper.check_changed(version, files + ["automation/css/revenue.py"])

    def test_manual_pr_requires_owner_approval_and_main(self):
        for key, value in (
            ("GITHUB_EVENT_NAME", "push"),
            ("GITHUB_REF", "refs/heads/feature"),
            ("GITHUB_ACTOR", "unknown"),
            ("LEGACY_BUILD_APPROVAL", "YES"),
            ("GITHUB_RUN_ID", "invalid;id"),
        ):
            env = good_env()
            env[key] = value
            with self.subTest(key=key), self.assertRaises(PermissionError):
                helper.authorize("7420", env)
        with self.assertRaises(PermissionError):
            helper.authorize("0000", good_env())
        self.assertEqual(helper.authorize("7422", good_env()),
                         "automation/kalman-build-7422-pr-44900123456")

    def test_no_change_skips_git_write(self):
        with tempfile.TemporaryDirectory() as td, patch.object(helper, "run", side_effect=AssertionError):
            self.assertEqual(helper.propose(Path(td), "7421", {"changed_paths": []}, good_env()), "NO_CHANGE")

    def test_manual_draft_proposal_only_pushes_feature_branch(self):
        paths = helper.files_for("7420")
        calls = []

        def mock_run(root, *args):
            calls.append(args)
            if args[:3] == ("git", "diff", "--cached"):
                return "\n".join(paths)
            if args[:3] == ("gh", "pr", "create"):
                return "https://github.com/kimtk94/Codex/pull/000"
            return ""

        with tempfile.TemporaryDirectory() as td, patch.object(helper, "run", side_effect=mock_run):
            branch = helper.propose(Path(td), "7420", {"changed_paths": paths}, good_env())
        self.assertEqual(branch, "automation/kalman-build-7420-pr-44900123456")
        pushes = [x for x in calls if x[:2] == ("git", "push")]
        self.assertEqual(pushes, [("git", "push", "origin",
                                   "HEAD:refs/heads/automation/kalman-build-7420-pr-44900123456")])
        self.assertTrue(any(x[:3] == ("gh", "pr", "create") and "--draft" in x for x in calls))

    def test_report_checks_and_preview_files(self):
        version = "7421"
        config = helper.VERSIONS[version]
        paths = helper.files_for(version)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for path in paths:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / paths[0]).write_bytes(b"source fixture\n")
            (root / paths[1]).write_bytes(b"compact fixture\n")
            report = {
                "version": config["target"],
                **config["assertions"],
                "compact_manifest_bytes": config["max_compact"] - 1,
                "source_manifest_sha256": hashlib.sha256((root / paths[0]).read_bytes()).hexdigest(),
                "vercel_manifest_sha256": hashlib.sha256((root / paths[1]).read_bytes()).hexdigest(),
            }
            (root / paths[2]).write_text(json.dumps(report), encoding="utf-8")

            def fake_run(_root, *args):
                if args[:3] == ("git", "ls-files", "--"):
                    return "\n".join(paths)
                if args[:3] == ("git", "diff", "--name-only"):
                    return "\n".join(paths)
                if args[:3] == ("git", "diff", "--binary"):
                    return "patch fixture"
                return ""

            with patch.object(helper, "run", side_effect=fake_run):
                preview = helper.preview(root, version, root / "artifacts")
            self.assertEqual(preview["decision"], "HUMAN_REVIEW_REQUIRED")
            self.assertEqual(preview["changed_paths"], paths)
            self.assertFalse(preview["direct_push_main"])
            self.assertTrue((root / "artifacts" / "kalman-build-7421.json").is_file())
            self.assertTrue((root / "artifacts" / "kalman-build-7421.patch").is_file())


if __name__ == "__main__":
    unittest.main()
