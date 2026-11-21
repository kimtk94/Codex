import json
import tempfile
import unittest
from pathlib import Path
from automation.ops.audit_main_writes import classify_line, scan_workflows


class MainWriteAuditTests(unittest.TestCase):
    def test_literal_direct_main_push(self):
        for line in (
            "git push origin HEAD:main",
            "git push origin HEAD:refs/heads/main",
            "git push --force-with-lease origin HEAD:main",
            "git push origin main",
        ):
            with self.subTest(line=line):
                self.assertEqual(classify_line(line), "CONFIRMED_MAIN_PUSH")

    def test_unknown_target_flags_hold(self):
        self.assertEqual(classify_line("git push origin HEAD:$TARGET_BRANCH"), "DYNAMIC_OR_UNKNOWN_PUSH")
        self.assertEqual(classify_line('git -C "$REPO" push origin "$REF"'), "DYNAMIC_OR_UNKNOWN_PUSH")

    def test_specific_feature_branch_is_not_direct_main(self):
        self.assertEqual(
            classify_line("git push origin HEAD:refs/heads/automation/test-123"),
            "EXPLICIT_OTHER_BRANCH_PUSH",
        )

    def test_ref_api_write_is_reported(self):
        self.assertEqual(
            classify_line("gh api --method PATCH repos/x/y/git/refs/heads/main"),
            "REF_API_WRITE",
        )

    def test_comment_is_not_command(self):
        self.assertIsNone(classify_line("# git push origin HEAD:main"))
        self.assertIsNone(classify_line("echo hello"))

    def test_audit_all_workflow_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wf = root / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "direct.yml").write_text(
                "name: direct\njobs:\n  test:\n    steps:\n      - run: git push origin HEAD:main\n",
                encoding="utf-8",
            )
            (wf / "dynamic.yaml").write_text(
                "name: dynamic\njobs:\n  test:\n    steps:\n      - run: git push origin HEAD:$TARGET\n",
                encoding="utf-8",
            )
            (wf / "feature.yml").write_text(
                "name: feature\njobs:\n  test:\n    steps:\n      - run: git push origin HEAD:refs/heads/sandbox/proposal\n",
                encoding="utf-8",
            )
            result = scan_workflows(root)
            self.assertEqual(result["workflow_files_scanned"], 3)
            self.assertEqual(result["direct_main_write_count"], 1)
            self.assertEqual(result["unknown_push_count"], 1)
            self.assertEqual(result["other_branch_push_count"], 1)
            self.assertEqual(result["classification"], "HOLD")
            self.assertTrue(result["limitations"])
            self.assertFalse(result["actions_performed"]["branch_protection_mutation"])
            self.assertEqual({x["line"] for x in result["findings"]}, {5})
            self.assertNotIn("git push", json.dumps(result["findings"]))

    def test_empty_directory_cannot_masquerade_as_clean(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".github" / "workflows").mkdir(parents=True)
            with self.assertRaises(ValueError):
                scan_workflows(root)


if __name__ == "__main__":
    unittest.main()
