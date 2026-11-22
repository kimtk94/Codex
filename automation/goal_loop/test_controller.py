"""Isolated negative and positive safety-contract tests (never calls Ollama/GitHub)."""
import io
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
    literal_contract_examples, retry_temperature, pr_head_relation,
    select_local_model, require_local_model,
    ollama_generation_timeout, ollama_proposal,
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
            if args[:2] == ["git", "merge-base"]:
                return {"ok": False, "code": 1, "output": ""}
            return {"ok": True, "code": 0, "output": "b" * 40}
        with patch("automation.goal_loop.controller.run_cmd", side_effect=fake_cmd):
            with self.assertRaisesRegex(Hold, "PR_HEAD_SHA_DIVERGED"):
                pr_checks(self.root, self.load(), "https://github.com/kimtk94/Codex/pull/123", time.monotonic() + 5, "a" * 40)

    def test_unverifiable_pr_head_fails_closed(self):
        with patch("automation.goal_loop.controller.run_cmd",
                   return_value={"ok": False, "code": 128, "output": ""}):
            with self.assertRaisesRegex(Hold, "PR_HEAD_ANCESTRY_UNVERIFIED"):
                pr_head_relation(self.root, "b" * 40, "a" * 40)

    def test_stale_pr_head_is_retried_until_expected_head_is_visible(self):
        old_sha = "a" * 40
        expected = "b" * 40
        calls = {"pr": 0, "api": 0}
        checks = [{
            "name": name, "head_sha": expected, "status": "completed",
            "conclusion": "success", "app": {"slug": "github-actions"},
        } for name in BASE["required_checks"]]

        def fake_cmd(args, *unused, **kwargs):
            if args[:3] == ["gh", "pr", "view"]:
                calls["pr"] += 1
                return {"ok": True, "code": 0,
                        "output": old_sha if calls["pr"] == 1 else expected}
            if args[:2] == ["git", "merge-base"]:
                self.assertEqual(args[-2:], [old_sha, expected])
                return {"ok": True, "code": 0, "output": ""}
            if args[:2] == ["gh", "api"]:
                calls["api"] += 1
                return {"ok": True, "code": 0,
                        "output": json.dumps({"check_runs": checks})}
            raise AssertionError(args)

        with patch("automation.goal_loop.controller.run_cmd", side_effect=fake_cmd), \
             patch("automation.goal_loop.controller.time.sleep"):
            state, _ = pr_checks(
                self.root, self.load(),
                "https://github.com/kimtk94/Codex/pull/123",
                time.monotonic() + 5, expected,
            )
        self.assertEqual(state, "PASS")
        self.assertEqual(calls["pr"], 3)
        self.assertEqual(calls["api"], 1)

    def test_real_git_head_ancestry_classification(self):
        # Verify local Git's actual exit semantics, not only mocked commands.
        root = self.root
        for cmd in (
            ["git", "init", "-q"],
            ["git", "add", "-A"],
            ["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid",
             "commit", "-q", "-m", "baseline"],
        ):
            self.assertTrue(run_cmd(cmd, root)["ok"], cmd)
        original = run_cmd(["git", "rev-parse", "HEAD"], root)["output"].strip()
        self.file.write_text("x = 2\n", encoding="utf-8")
        for cmd in (
            ["git", "add", "-A"],
            ["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid",
             "commit", "-q", "-m", "agent improvement"],
        ):
            self.assertTrue(run_cmd(cmd, root)["ok"], cmd)
        improved = run_cmd(["git", "rev-parse", "HEAD"], root)["output"].strip()
        self.assertEqual(pr_head_relation(root, original, improved), "STALE_PR_API")
        self.assertEqual(pr_head_relation(root, improved, original), "REMOTE_ADVANCED")
        self.assertEqual(pr_head_relation(root, improved, improved), "MATCH")

    def test_remote_advanced_does_not_attest_stale_commit(self):
        expected = "a" * 40
        advanced = "b" * 40
        calls = {"merge": 0}
        def fake_cmd(args, *unused, **kwargs):
            if args[:3] == ["gh", "pr", "view"]:
                return {"ok": True, "code": 0, "output": advanced}
            if args[:2] == ["git", "merge-base"]:
                calls["merge"] += 1
                return {"ok": calls["merge"] == 2,
                        "code": 1 if calls["merge"] == 1 else 0,
                        "output": ""}
            raise AssertionError("Must not query stale CI: " + repr(args))

        with patch("automation.goal_loop.controller.run_cmd", side_effect=fake_cmd):
            state, checks = pr_checks(
                self.root, self.load(),
                "https://github.com/kimtk94/Codex/pull/123",
                time.monotonic() + 5, expected,
            )
        self.assertEqual(state, "HEAD_ADVANCED")
        self.assertEqual(checks, [])


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

    def test_literal_acceptance_aliases_ast_only(self):
        acceptance = self.root / "automation/goal_loop/pilot_acceptance.py"
        acceptance.write_text(
            "import unittest\n"
            "class Contract(unittest.TestCase):\n"
            "  def test_pass(self):\n"
            "    for raw in (' pass ', 'PASSED', 'ok', 'done', 'success'):\n"
            "      with self.subTest(raw=raw):\n"
            "        self.assertEqual(normalize_status(raw), 'PASS')\n"
            "  def test_fail(self):\n"
            "    for raw in ('failed', 'FAIL', 'error'):\n"
            "      self.assertEqual(normalize_status(raw), 'FAIL')\n"
            "  def test_other(self):\n"
            "    for raw in ('unknown', '', None, {}, 42):\n"
            "      self.assertEqual(normalize_status(raw), 'HOLD')\n",
            encoding="utf-8",
        )
        examples = literal_contract_examples(self.root, self.load())
        self.assertEqual(len(examples), 13)
        self.assertEqual(
            [(x["input"], x["expected"]) for x in examples[:5]],
            [(" pass ", "PASS"), ("PASSED", "PASS"), ("ok", "PASS"),
             ("done", "PASS"), ("success", "PASS")],
        )
        self.assertIn({"function": "normalize_status", "input": {}, "expected": "HOLD"}, examples)
        self.assertIn({"function": "normalize_status", "input": 42, "expected": "HOLD"}, examples)

    def test_literal_examples_never_execute_test_side_effect(self):
        acceptance = self.root / "automation/goal_loop/pilot_acceptance.py"
        forbidden = self.root / "MUST_NOT_EXIST.txt"
        acceptance.write_text(
            "from pathlib import Path\n"
            f"Path({str(forbidden)!r}).write_text('danger')\n"
            "for raw in ('yes',):\n"
            "    self.assertEqual(normalize_status(raw), 'PASS')\n",
            encoding="utf-8",
        )
        self.assertEqual(
            literal_contract_examples(self.root, self.load()),
            [{"function": "normalize_status", "input": "yes", "expected": "PASS"}],
        )
        self.assertFalse(forbidden.exists())

    def test_literal_examples_skip_computed_inputs(self):
        acceptance = self.root / "automation/goal_loop/pilot_acceptance.py"
        acceptance.write_text(
            "for raw in load_external_cases():\n"
            "    self.assertEqual(normalize_status(raw), 'PASS')\n",
            encoding="utf-8",
        )
        self.assertEqual(literal_contract_examples(self.root, self.load()), [])

    def test_adaptive_retry_temperature_is_bounded(self):
        self.assertEqual(retry_temperature({}), 0.1)
        self.assertEqual(retry_temperature({"no_change_count": 1}), 0.3)
        self.assertEqual(retry_temperature({"no_change_count": 2}), 0.5)
        self.assertEqual(retry_temperature({"no_change_count": 10}), 0.5)
        self.assertEqual(retry_temperature({"no_change_count": "invalid"}), 0.1)

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

    def test_bounded_ollama_request_timeout_for_opt_in_7b(self):
        self.assertEqual(ollama_generation_timeout("qwen25coder3b-16k"), 200)
        self.assertEqual(ollama_generation_timeout("qwen2.5-coder:7b"), 600)
        self.assertEqual(ollama_generation_timeout("unrecognized"), 200)

    def test_ollama_timeout_records_model_and_limit(self):
        with patch("automation.goal_loop.controller.select_local_model",
                   return_value="qwen2.5-coder:7b"), \
             patch("automation.goal_loop.controller.urllib.request.urlopen",
                   side_effect=TimeoutError("model slow")) as call:
            with self.assertRaisesRegex(
                Hold,
                r"LOCAL_OLLAMA_GENERATION_TIMEOUT:model=qwen2[.]5-coder:7b:limit=600",
            ):
                ollama_proposal(self.root, self.load(), {"verification": "REMOTE_CI_ONLY"})
        self.assertEqual(call.call_args.kwargs["timeout"], 600)

    def test_ollama_request_timeout_is_default_for_3b(self):
        reply = {"message": {"content": json.dumps({
            "path": BASE["allowed_files"][0], "content": "x = 2\n",
        })}}
        with patch("automation.goal_loop.controller.select_local_model",
                   return_value="qwen25coder3b-16k"), \
             patch("automation.goal_loop.controller.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(reply).encode())) as call:
            value = ollama_proposal(self.root, self.load(), {})
        self.assertEqual(value["content"], "x = 2\n")
        self.assertEqual(call.call_args.kwargs["timeout"], 200)

    def test_override_model_remains_explicitly_allowlisted(self):
        goal = self.load()
        self.assertEqual(select_local_model(goal, {}), goal.get("model", "qwen25coder3b-16k"))
        self.assertEqual(select_local_model(goal, {"GOAL_LOOP_MODEL": "qwen2.5-coder:7b"}),
                         "qwen2.5-coder:7b")
        with self.assertRaisesRegex(Hold, "MODEL_OVERRIDE_NOT_ALLOWED"):
            select_local_model(goal, {"GOAL_LOOP_MODEL": "arbitrary/unsafe:latest"})
        self.assertEqual(goal["goal_id"], BASE["goal_id"])

    def test_local_model_presence_in_ollama_is_checked_read_only(self):
        models = {"models": [{"name": "qwen25coder3b-16k:latest"},
                              {"name": "qwen2.5-coder:7b"}]}
        with patch("automation.goal_loop.controller.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(models).encode())) as call:
            self.assertEqual(require_local_model("qwen2.5-coder:7b"),
                             "qwen2.5-coder:7b")
        self.assertIn("127.0.0.1:11434", call.call_args.args[0])
        with patch("automation.goal_loop.controller.urllib.request.urlopen",
                   return_value=io.BytesIO(b'{"models":[]}')):
            with self.assertRaisesRegex(Hold, "SELECTED_LOCAL_MODEL_NOT_INSTALLED"):
                require_local_model("qwen2.5-coder:7b")
        with patch("automation.goal_loop.controller.urllib.request.urlopen",
                   side_effect=ConnectionError("offline")):
            with self.assertRaisesRegex(Hold, "LOCAL_OLLAMA_MODEL_CHECK_FAILED"):
                require_local_model("qwen2.5-coder:7b")

    def test_no_ollama_model_does_not_consume_iteration_budget(self):
        with patch("pathlib.Path.home", return_value=self.root), \
             patch("automation.goal_loop.controller.require_local_model",
                   side_effect=Hold("SELECTED_LOCAL_MODEL_NOT_INSTALLED:qwen2.5-coder:7b")), \
             patch("automation.goal_loop.controller.run_cmd") as command:
            with self.assertRaisesRegex(Hold, "SELECTED_LOCAL_MODEL_NOT_INSTALLED"):
                run(self.root, self.load())
        command.assert_not_called()
        self.assertFalse((self.root / ".goal-loop").exists())

    def test_repeated_identical_model_output_uses_attempt_budget_not_exception(self):
        def safe_fake_command(args, *unused, **kwargs):
            if args[:4] == ["git", "remote", "get-url", "origin"]:
                return {"ok": True, "code": 0, "output": "https://github.com/kimtk94/Codex.git\n"}
            return {"ok": True, "code": 0, "output": ""}
        with patch("pathlib.Path.home", return_value=self.root), \
             patch("automation.goal_loop.controller.shutil.which", return_value="fake-binary"), \
             patch("automation.goal_loop.controller.require_local_model", return_value="qwen25coder3b-16k"), \
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
