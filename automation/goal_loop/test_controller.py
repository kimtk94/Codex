"""Isolated negative and positive safety-contract tests (never calls Ollama/GitHub)."""
import json
import subprocess
import sys
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation.goal_loop.controller import (
    Hold, apply_proposal, check_worktree_scope, failed_required_checks,
    load_goal, parse_porcelain_paths, run, run_cmd, test_goal, pr_checks,
    unsafe_ci_gate_failed, verification_source_context,
)


BASE = {
    "version": 1,
    "goal_id": "pilot-status-normalizer",
    "document": "docs/automation/goal-loop-pilot.md",
    "repo": "kimtk94/Codex",
    "base_branch": "main",
    "allowed_files": ["automation/goal_loop/pilot_target.py"],
    "verify": [["python", "-m", "unittest", "automation.goal_loop.pilot_acceptance", "-v"]],
    "required_checks": ["goal-loop-controller-tests", "pilot-acceptance", "main-write-guard"],
    "max_iterations": 3,
    "max_minutes": 45,
}


class ControllerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = self.root / BASE["document"]
        self.doc.parent.mkdir(parents=True)
        self.doc.write_text("# Objective\n", encoding="utf-8")
        self.file = self.root / BASE["allowed_files"][0]
        self.file.parent.mkdir(parents=True)
        self.file.write_text("x = 1\n", encoding="utf-8")
        self.config = self.root / "goal.json"
        self.save(BASE)

    def save(self, obj):
        self.config.write_text(json.dumps(obj), encoding="utf-8")

    def load(self):
        return load_goal(self.root, "goal.json")

    def test_valid_goal(self):
        self.assertEqual(self.load()["goal_id"], BASE["goal_id"])

    def test_outside_path_rejected(self):
        self.save({**BASE, "allowed_files": ["../steal.py"]})
        with self.assertRaises(Hold):
            self.load()

    def test_workflow_edits_rejected(self):
        path = ".github/workflows/ci.yml"
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / path).write_text("name: test\n")
        self.save({**BASE, "allowed_files": [path]})
        with self.assertRaises(Hold):
            self.load()

    def test_no_ci_proof_rejected(self):
        self.save({**BASE, "required_checks": ["pilot-acceptance"]})
        with self.assertRaises(Hold):
            self.load()

    def test_shell_metacharacters_rejected(self):
        self.save({**BASE, "verify": [["python", "-m", "unittest", "test_x;rm -rf /"]]})
        with self.assertRaises(Hold):
            self.load()

    def test_apply_edit_exact_allowlist(self):
        p = apply_proposal(self.root, self.load(), {
            "path": BASE["allowed_files"][0], "content": "x = 2\n",
        })
        self.assertEqual(p, BASE["allowed_files"][0])
        self.assertEqual(self.file.read_text(), "x = 2\n")

    def test_edit_tests_rejected(self):
        with self.assertRaises(Hold):
            apply_proposal(self.root, self.load(), {
                "path": "automation/goal_loop/pilot_acceptance.py", "content": "x=2\n",
            })

    def test_model_syntax_error_preserves_original(self):
        with self.assertRaises(Hold):
            apply_proposal(self.root, self.load(), {
                "path": BASE["allowed_files"][0], "content": "def bad(:\n",
            })
        self.assertEqual(self.file.read_text(), "x = 1\n")

    def test_possible_secret_leak_rejected(self):
        with self.assertRaises(Hold):
            apply_proposal(self.root, self.load(), {
                "path": BASE["allowed_files"][0],
                "content": "token='ghp_1234567890123456789012345678'\n",
            })
        self.assertEqual(self.file.read_text(), "x = 1\n")

    def test_local_execution_always_forbidden(self):
        with self.assertRaisesRegex(Hold, "LOCAL_TEST_EXECUTION_FORBIDDEN"):
            test_goal(self.root, self.load())

    def test_symlink_is_not_editable(self):
        self.file.unlink()
        external = self.root / "external.py"
        external.write_text("x = 1\n")
        try:
            self.file.symlink_to(external)
        except OSError:
            self.skipTest("Windows symlink creation may require administrator privileges")
        with self.assertRaisesRegex(Hold, "MISSING_OR_LINKED_EDIT_TARGET"):
            self.load()

    def test_remote_ci_pass_requires_exact_sha(self):
        sha = "a" * 40
        checks = [{
            "name": name, "status": "completed", "conclusion": "success",
            "head_sha": sha, "id": index, "app": {"slug": "github-actions"},
            "html_url": "https://github.com/kimtk94/Codex/actions",
        } for index, name in enumerate(BASE["required_checks"])]
        def fake_cmd(args, *unused, **kwargs):
            if args[1:3] == ["pr", "view"]:
                return {"ok": True, "output": sha}
            if args[1] == "api":
                return {"ok": True, "output": json.dumps({"check_runs": checks})}
            raise AssertionError("unexpected command")
        with patch("automation.goal_loop.controller.run_cmd", side_effect=fake_cmd):
            state, observed = pr_checks(self.root, self.load(), "https://github.com/kimtk94/Codex/pull/123", time.monotonic() + 5, sha)
        self.assertEqual(state, "PASS")
        self.assertEqual(len(observed), 3)

    def test_remote_ci_non_github_app_cannot_attest(self):
        sha = "a" * 40
        checks = [{
            "name": name, "status": "completed", "conclusion": "success",
            "head_sha": sha, "id": index, "app": {"slug": "untrusted-app"},
            "html_url": "https://github.com/kimtk94/Codex/actions",
        } for index, name in enumerate(BASE["required_checks"])]
        def fake_cmd(args, *unused, **kwargs):
            if args[1:3] == ["pr", "view"]:
                return {"ok": True, "output": sha}
            return {"ok": True, "output": json.dumps({"check_runs": checks})}
        with patch("automation.goal_loop.controller.run_cmd", side_effect=fake_cmd), \
             patch("automation.goal_loop.controller.time.sleep"):
            state, _ = pr_checks(self.root, self.load(), "https://github.com/kimtk94/Codex/pull/123", time.monotonic() + 0.01, sha)
        self.assertEqual(state, "TIMEOUT")

    def test_remote_ci_wrong_head_fails_closed(self):
        def fake_cmd(args, *unused, **kwargs):
            return {"ok": True, "output": "b" * 40}
        with patch("automation.goal_loop.controller.run_cmd", side_effect=fake_cmd):
            with self.assertRaisesRegex(Hold, "PR_HEAD_SHA_MISMATCH"):
                pr_checks(self.root, self.load(), "https://github.com/kimtk94/Codex/pull/123", time.monotonic() + 5, "a" * 40)

    def test_remote_ci_wrong_check_sha_is_not_pass(self):
        head = "a" * 40
        bad = [{
            "name": name, "status": "completed", "conclusion": "success",
            "head_sha": "b" * 40, "app": {"slug": "github-actions"},
            "html_url": "https://github.com/kimtk94/Codex/actions",
        } for name in BASE["required_checks"]]
        def fake_cmd(args, *unused, **kwargs):
            if args[1:3] == ["pr", "view"]:
                return {"ok": True, "output": head}
            return {"ok": True, "output": json.dumps({"check_runs": bad})}
        with patch("automation.goal_loop.controller.run_cmd", side_effect=fake_cmd), \
             patch("automation.goal_loop.controller.time.sleep"):
            state, _ = pr_checks(self.root, self.load(), "https://github.com/kimtk94/Codex/pull/123", time.monotonic() + 0.01, head)
        self.assertEqual(state, "TIMEOUT")

    def test_porcelain_preserves_leading_space_in_unstaged_modification(self):
        status = " M automation/goal_loop/pilot_target.py\0"
        self.assertEqual(parse_porcelain_paths(status), [BASE["allowed_files"][0]])

    def test_porcelain_preserves_stage_and_untracked_entries(self):
        self.assertEqual(
            parse_porcelain_paths(
                "M  automation/goal_loop/pilot_target.py\0"
                "?? docs/accidental.md\0"
            ),
            [BASE["allowed_files"][0], "docs/accidental.md"],
        )
        self.assertEqual(
            parse_porcelain_paths(
                "R  automation/goal_loop/pilot_target.py\0"
                "automation/goal_loop/old_target.py\0"
            ),
            [BASE["allowed_files"][0], "automation/goal_loop/old_target.py"],
        )

    def test_porcelain_rejects_partial_or_malformed_status(self):
        for status in (
            " M automation/goal_loop/pilot_target.py",
            "R  automation/goal_loop/pilot_target.py\0",
            "invalid\0",
        ):
            with self.subTest(status=status), self.assertRaises(Hold):
                parse_porcelain_paths(status)

    def test_worktree_scope_allows_only_exact_target_and_blocks_untracked(self):
        name = BASE["allowed_files"][0]
        with patch("automation.goal_loop.controller.run_cmd",
                   return_value={"ok": True, "output": " M " + name + "\0"}) as call:
            self.assertEqual(check_worktree_scope(self.root, self.load()), [name])
        self.assertIn("-z", call.call_args.args[0])
        with patch("automation.goal_loop.controller.run_cmd",
                   return_value={"ok": True, "output": " M " + name + "\0?? .env\0"}):
            with self.assertRaisesRegex(Hold, "UNEXPECTED_WORKTREE_CHANGE"):
                check_worktree_scope(self.root, self.load())

    def test_real_git_status_in_temp_worktree_matches_allowlist(self):
        # Reproduces the exact leading-space porcelain status that caused HOLD.
        root = self.root
        for args in (
            ["git", "init", "-q"],
            ["git", "add", "-A"],
            ["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid",
             "commit", "-q", "-m", "baseline"],
        ):
            self.assertTrue(run_cmd(args, root)["ok"], args)
        self.file.write_text("x = 2\n", encoding="utf-8")
        self.assertEqual(
            check_worktree_scope(root, self.load()),
            [BASE["allowed_files"][0]],
        )

    def test_subprocess_replaces_undecodable_bytes_on_windows(self):
        # A real child emits an invalid cp949/UTF-8 byte in both streams.
        # Previously this crashed the reader thread and returned None.
        child = [
            sys.executable, "-c",
            "import sys;sys.stdout.buffer.write(bytes([130]));"
            "sys.stderr.buffer.write(bytes([130]))",
        ]
        actual = run_cmd(child, self.root)
        self.assertTrue(actual["ok"])
        self.assertIn("\ufffd", actual["output"])
        self.assertIn("\ufffd", actual["stderr"])

    def test_subprocess_empty_streams_never_crash(self):
        with patch("automation.goal_loop.controller.subprocess.run",
                   return_value=subprocess.CompletedProcess(["gh"], 0, None, None)) as proc:
            actual = run_cmd(["gh", "auth", "status"], self.root)
        self.assertEqual(actual["output"], "")
        self.assertEqual(actual["stderr"], "")
        self.assertEqual(proc.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(proc.call_args.kwargs["errors"], "replace")

    def test_subprocess_failed_command_returns_safe_hold(self):
        with patch("automation.goal_loop.controller.subprocess.run",
                   return_value=subprocess.CompletedProcess(["gh"], 1, None, None)):
            with self.assertRaisesRegex(Hold, "COMMAND_FAILED:gh"):
                run_cmd(["gh", "auth", "status"], self.root, checked=True)

    def test_provide_read_only_acceptance_file_context(self):
        test_path = self.root / "automation/goal_loop/pilot_acceptance.py"
        test_path.write_text("assert expected_alias == 'PASS'\n", encoding="utf-8")
        sources = verification_source_context(self.root, self.load())
        self.assertEqual(
            sources["automation/goal_loop/pilot_acceptance.py"],
            test_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(test_path.read_text(encoding="utf-8"), sources[
            "automation/goal_loop/pilot_acceptance.py"
        ])

    def test_ci_pilot_failure_is_retryable_but_security_failure_blocks(self):
        goal = self.load()
        def item(name, app="github-actions"):
            return {"name": name, "app_slug": app, "conclusion": "failure"}
        self.assertFalse(unsafe_ci_gate_failed(goal, [item("pilot-acceptance")]))
        self.assertTrue(unsafe_ci_gate_failed(goal, [item("main-write-guard")]))
        self.assertTrue(unsafe_ci_gate_failed(goal, [item("goal-loop-controller-tests")]))
        self.assertEqual(
            failed_required_checks(goal, [item("pilot-acceptance")]),
            ["pilot-acceptance"],
        )
        self.assertFalse(unsafe_ci_gate_failed(goal, [item("unrelated")]))
        self.assertFalse(unsafe_ci_gate_failed(goal, [item("main-write-guard", "external-app")]))

    def test_repeated_identical_model_output_uses_attempt_budget_not_exception(self):
        def safe_fake_command(args, *unused, **kwargs):
            if args[:4] == ["git", "remote", "get-url", "origin"]:
                return {"ok": True, "code": 0, "output": "https://github.com/kimtk94/Codex.git\n"}
            return {"ok": True, "code": 0, "output": ""}
        with patch("pathlib.Path.home", return_value=self.root), \
             patch("automation.goal_loop.controller.shutil.which", return_value="fake-binary"), \
             patch("automation.goal_loop.controller.run_cmd", side_effect=safe_fake_command), \
             patch("automation.goal_loop.controller.ollama_proposal",
                   return_value={"path": BASE["allowed_files"][0], "content": "x = 1\n"}) as model, \
             patch("automation.goal_loop.controller.apply_proposal",
                   side_effect=Hold("MODEL_NO_CHANGE")):
            result = run(self.root, self.load())
        self.assertEqual(result["state"], "NO_PROGRESS_HOLD")
        self.assertEqual(len(result["evidence"]["iterations"]), 3)
        self.assertTrue(all(i.get("no_change") for i in result["evidence"]["iterations"]))
        self.assertEqual(model.call_count, 3)

    def test_dry_run_does_not_call_model_or_git(self):
        with patch("pathlib.Path.home", return_value=self.root), \
             patch("automation.goal_loop.controller.ollama_proposal") as model, \
             patch("automation.goal_loop.controller.run_cmd") as command:
            result = run(self.root, self.load(), dry_run=True)
        self.assertEqual(result["state"], "READY")
        self.assertFalse((self.root / ".goal-loop").exists())
        model.assert_not_called()
        command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
