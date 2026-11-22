"""V2 static-quality and isolated-goal contract tests (never execute model code)."""
import json
from pathlib import Path
import tempfile
import unittest

from automation.goal_loop.controller import (
    Hold, acceptance_check_name, apply_proposal, load_goal,
    unsafe_ci_gate_failed,
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

    def test_apply_proposal_quality_accepts_nonexecuted_source(self):
        goal = self.parsed_goal()
        self.assertEqual(apply_proposal(self.root, goal,
                         {"path": goal["allowed_files"][0], "content": VALID_SOURCE}),
                         goal["allowed_files"][0])
        self.assertEqual((self.root / goal["allowed_files"][0]).read_text(encoding="utf-8"),
                         VALID_SOURCE)


if __name__ == "__main__":
    unittest.main()
