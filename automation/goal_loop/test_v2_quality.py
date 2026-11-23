"""V2 static-quality and isolated-goal contract tests (never execute model code)."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation.goal_loop.controller import (
    Hold, acceptance_check_name, apply_proposal, load_goal, run,
    ollama_proposal, v2_compact_prompt, unsafe_ci_gate_failed,
)
from automation.goal_loop.source_quality import (
    SourceQualityError, validate_v2_source,
)


VALID_SOURCE = '''"""Safe module docstring."""

def normalize_status(value):
    if not isinstance(value, str):
        return "HOLD"
    normalized = value.strip().upper()
    if normalized in ("PASS", "PASSED", "OK", "DONE", "SUCCESS"):
        return "PASS"
    if normalized in ("FAIL", "FAILED", "ERROR"):
        return "FAIL"
    return "HOLD"
'''


class V2QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.goal = {
            "version": 1, "goal_id": "pilot-status-normalizer-v2",
            "document": "docs/automation/goal-loop-pilot-v2.md",
            "repo": "kimtk94/Codex", "base_branch": "main",
            "allowed_files": ["automation/goal_loop/pilot_target_v2.py"],
            "verify": [["python", "-m", "unittest",
                        "automation.goal_loop.pilot_acceptance_v2", "-v"]],
            "required_checks": ["goal-loop-controller-tests",
                                "pilot-acceptance-v2", "main-write-guard"],
            "max_iterations": 2, "max_minutes": 35,
        }
        for path, content in (
            (self.goal["document"], "# V2 pilot\n"),
            (self.goal["allowed_files"][0], "def normalize_status(value):\n    return 'HOLD'\n"),
            ("automation/goal_loop/pilot_acceptance_v2.py", "# static read-only\n"),
        ):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.config = self.root / "v2.json"
        self.save_goal(self.goal)

    def save_goal(self, content):
        self.config.write_text(json.dumps(content), encoding="utf-8")

    def parsed_goal(self):
        return load_goal(self.root, "v2.json")

    def write_realistic_acceptance_cases(self):
        path = self.root / "automation/goal_loop/pilot_acceptance_v2.py"
        path.write_text(
            "for raw in (' pass ', 'PASSED', 'ok', 'DONE', 'Success'):\n"
            "    self.assertEqual(normalize_status(raw), 'PASS')\n"
            "for raw in ('fail', 'Failed', ' ERROR '):\n"
            "    self.assertEqual(normalize_status(raw), 'FAIL')\n"
            "for raw in ('UNKNOWN', '', None, {}, 42, True, []):\n"
            "    self.assertEqual(normalize_status(raw), 'HOLD')\n"
            "# UNTRUSTED_FULL_TEST_BODY_SHOULD_NOT_BE_IN_PROMPT\n",
            encoding="utf-8",
        )

    def test_v2_prompt_minimizes_ci_logs_but_preserves_literal_examples(self):
        self.write_realistic_acceptance_cases()
        goal = self.parsed_goal()
        feedback = {
            "last_static_rejection": "MODEL_V2_SOURCE_QUALITY:V2_MISSING_CANONICAL_OUTPUTS",
            "previous_checks": {
                "verdict": "FAIL",
                "checks": [{"name": "pilot-acceptance-v2",
                            "conclusion": "failure", "untrusted_log_excerpt":
                            "UNTRUSTED_LARGE_CI_LOG_SECRET_SENTINEL"}],
            },
            "failures": [{"untrusted_log_excerpt": "UNTRUSTED_LARGE_CI_LOG_SECRET_SENTINEL"}],
        }
        target = goal["allowed_files"][0]
        source = {target: (self.root / target).read_text(encoding="utf-8")}
        prompt = v2_compact_prompt(self.root, goal, feedback, source)
        self.assertLess(len(prompt), 5000)
        self.assertIn("PASSED", prompt)
        self.assertIn("Failed", prompt)
        self.assertIn("UNKNOWN", prompt)
        self.assertIn("V2_MISSING_CANONICAL_OUTPUTS", prompt)
        self.assertNotIn("UNTRUSTED_LARGE_CI_LOG_SECRET_SENTINEL", prompt)
        self.assertNotIn("UNTRUSTED_FULL_TEST_BODY_SHOULD_NOT_BE_IN_PROMPT", prompt)

    def test_v2_small_model_request_caps_context_and_generation(self):
        self.write_realistic_acceptance_cases()
        goal = self.parsed_goal()
        reply = {"message": {"content": json.dumps({
            "path": goal["allowed_files"][0], "content": VALID_SOURCE
        })}, "prompt_eval_count": 920, "eval_count": 130}
        with patch("automation.goal_loop.controller.select_local_model",
                   return_value="qwen25coder3b-16k"), \
             patch("automation.goal_loop.controller.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(reply).encode("utf-8"))) as request:
            result = ollama_proposal(self.root, goal, {"previous_checks": {"verdict": "FAIL"}})
        self.assertEqual(result["content"], VALID_SOURCE)
        self.assertEqual(request.call_args.kwargs["timeout"], 200)
        outgoing = json.loads(request.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(outgoing["options"]["num_ctx"], 4096)
        self.assertEqual(outgoing["options"]["num_predict"], 512)
        self.assertEqual(outgoing["keep_alive"], "5m")
        self.assertEqual(outgoing["model"], "qwen25coder3b-16k")
        self.assertLess(len(outgoing["messages"][1]["content"]), 5000)

    def test_v2_prompt_requires_independent_expected_outputs(self):
        with self.assertRaisesRegex(Hold, "V2_INDEPENDENT_EXAMPLES_UNAVAILABLE"):
            v2_compact_prompt(self.root, self.parsed_goal(), {}, {
                self.goal["allowed_files"][0]: "def normalize_status(value):\n    return 'HOLD'\n"
            })

    def test_v2_is_independent_from_exhausted_v1(self):
        v2 = self.parsed_goal()
        self.assertEqual(acceptance_check_name(v2), "pilot-acceptance-v2")
        self.assertEqual(v2["goal_id"], "pilot-status-normalizer-v2")
        self.assertTrue(unsafe_ci_gate_failed(v2, [{
            "name": "main-write-guard", "conclusion": "failure",
            "app_slug": "github-actions",
        }]))
        self.assertFalse(unsafe_ci_gate_failed(v2, [{
            "name": "pilot-acceptance-v2", "conclusion": "failure",
            "app_slug": "github-actions",
        }]))

    def test_v2_goal_cannot_edit_v1_target_or_tests(self):
        for changes in (
            {"allowed_files": ["automation/goal_loop/pilot_target.py"]},
            {"allowed_files": ["automation/goal_loop/pilot_acceptance_v2.py"]},
            {"document": "docs/automation/goal-loop-pilot.md"},
            {"verify": [["python", "-m", "unittest",
                         "automation.goal_loop.pilot_acceptance", "-v"]]},
            {"required_checks": ["goal-loop-controller-tests",
                                 "pilot-acceptance", "main-write-guard"]},
        ):
            with self.subTest(changes=changes):
                self.save_goal({**self.goal, **changes})
                with self.assertRaises(Hold):
                    self.parsed_goal()
        self.save_goal(self.goal)

    def test_safe_source_shape_without_execution(self):
        result = validate_v2_source(VALID_SOURCE)
        self.assertTrue(result["module_level_safe"])
        self.assertEqual(result["function"], "normalize_status")

    def test_real_qwen_v2_identity_proposal_is_rejected_statically(self):
        # Exact model-output shape from PR #1007; no model code is imported.
        qwen = (
            "def normalize_status(value):\n"
            '    """Return PASS/FAIL/HOLD according to the independent V2 goal."""\n'
            '    return str(value).strip().upper() if isinstance(value, str) else "HOLD"\n'
        )
        with self.assertRaisesRegex(SourceQualityError, "V2_MISSING_CANONICAL_OUTPUTS"):
            validate_v2_source(qwen)
        goal = self.parsed_goal()
        target = self.root / goal["allowed_files"][0]
        before = target.read_text(encoding="utf-8")
        with self.assertRaisesRegex(Hold, "MODEL_V2_SOURCE_QUALITY:V2_MISSING_CANONICAL_OUTPUTS"):
            apply_proposal(self.root, goal, {"path": goal["allowed_files"][0], "content": qwen})
        self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_canonical_output_literals_are_required_but_not_sufficient(self):
        # This shape passes only a structural check; actual behavioral
        # correctness remains the authority of GitHub acceptance CI.
        fake = (
            "def normalize_status(value):\n"
            '    return "PASS" if value == "x" else "FAIL" if value == "y" else "HOLD"\n'
        )
        self.assertTrue(validate_v2_source(fake)["canonical_outputs_present"])
        for omitted in ("PASS", "FAIL", "HOLD"):
            source = fake.replace('"' + omitted + '"', '"WRONG"')
            with self.subTest(omitted=omitted), self.assertRaisesRegex(
                SourceQualityError, "V2_MISSING_CANONICAL_OUTPUTS"
            ):
                validate_v2_source(source)

    def test_v1_import_time_assert_is_statically_rejected(self):
        bad = VALID_SOURCE + "\nassert normalize_status('unknown') == 'HOLD'\n"
        with self.assertRaisesRegex(SourceQualityError,
                                    "V2_FORBIDDEN_MODULE_LEVEL_STATEMENT"):
            validate_v2_source(bad)

    def test_reject_other_module_level_side_effects(self):
        for source in (
            "import os\n" + VALID_SOURCE,
            "open('foo', 'w')\n" + VALID_SOURCE,
            "STATE = 1\n" + VALID_SOURCE,
            VALID_SOURCE + "\nprint('ready')\n",
            VALID_SOURCE + "\nclass Unsafe: pass\n",
            VALID_SOURCE + "\ndef extra(): pass\n",
        ):
            with self.subTest(source=source[:60]), self.assertRaises(SourceQualityError):
                validate_v2_source(source)

    def test_reject_dynamic_execution_inside_function(self):
        for line in ("return eval(value)", "return exec(value)",
                     "import os", "while True: pass", "global x"):
            source = "def normalize_status(value):\n    " + line + "\n"
            with self.subTest(line=line), self.assertRaises(SourceQualityError):
                validate_v2_source(source)

    def test_reject_missing_signature_or_return(self):
        for source in (
            "def normalize_status(value, extra):\n    return value\n",
            "def normalize_status(value):\n    pass\n",
            "def normalize_status(value):\n    return value\n"
            "@decorator\ndef extra(value):\n    return value\n",
        ):
            with self.subTest(source=source), self.assertRaises(SourceQualityError):
                validate_v2_source(source)

    def test_apply_proposal_quality_rejection_preserves_file(self):
        goal = self.parsed_goal()
        path = self.root / goal["allowed_files"][0]
        original = path.read_text(encoding="utf-8")
        bad = VALID_SOURCE + "\nassert normalize_status('unknown') == 'HOLD'\n"
        with self.assertRaisesRegex(Hold, "MODEL_V2_SOURCE_QUALITY"):
            apply_proposal(self.root, goal, {"path": goal["allowed_files"][0],
                                             "content": bad})
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_invalid_v2_model_source_retries_within_goal_budget(self):
        bad = VALID_SOURCE + "\\nassert normalize_status('unknown') == 'HOLD'\\n"
        def fake_command(args, *unused, **kwargs):
            if args[:4] == ["git", "remote", "get-url", "origin"]:
                return {"ok": True, "code": 0,
                        "output": "https://github.com/kimtk94/Codex.git\n"}
            return {"ok": True, "code": 0, "output": ""}
        with patch("pathlib.Path.home", return_value=self.root), \
             patch("automation.goal_loop.controller.require_local_model"), \
             patch("automation.goal_loop.controller.shutil.which", return_value="git"), \
             patch("automation.goal_loop.controller.run_cmd", side_effect=fake_command), \
             patch("automation.goal_loop.controller.apply_proposal",
                   side_effect=Hold("MODEL_V2_SOURCE_QUALITY:V2_FORBIDDEN_MODULE_LEVEL_STATEMENT")), \
             patch("automation.goal_loop.controller.ollama_proposal",
                   return_value={"path": self.goal["allowed_files"][0],
                                 "content": bad}) as model:
            result = run(self.root, self.parsed_goal())
        self.assertEqual(result["state"], "STATIC_QUALITY_HOLD")
        self.assertEqual(len(result["evidence"]["iterations"]), 2)
        self.assertEqual(model.call_count, 2)
        self.assertTrue(all(i["static_rejected"] for i in result["evidence"]["iterations"]))
        self.assertNotIn("pr_url", result["evidence"])

    def test_apply_proposal_quality_accepts_nonexecuted_source(self):
        goal = self.parsed_goal()
        self.assertEqual(apply_proposal(self.root, goal,
                         {"path": goal["allowed_files"][0], "content": VALID_SOURCE}),
                         goal["allowed_files"][0])
        self.assertEqual((self.root / goal["allowed_files"][0]).read_text(encoding="utf-8"),
                         VALID_SOURCE)


if __name__ == "__main__":
    unittest.main()
