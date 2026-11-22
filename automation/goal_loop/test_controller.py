"""Isolated negative and positive safety-contract tests (never calls Ollama/GitHub)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation.goal_loop.controller import Hold, apply_proposal, load_goal, run


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
