import tempfile
import unittest
from pathlib import Path

from automation.ops.main_write_pr_gate import evaluate


class MainWritePRGateTests(unittest.TestCase):
    def make_repo(self, root: Path, line: str, script: str | None = None) -> None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "demo.yml").write_text(
            "name: Demo\njobs:\n  check:\n    steps:\n      - run: " + line + "\n",
            encoding="utf-8",
        )
        if script is not None:
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "worker.py").write_text(script, encoding="utf-8")

    def test_clean_workflow_not_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root, "python -c 'print(123)'")
            result = evaluate(root)
            self.assertEqual(result["result"], "PASS_WITH_REVIEW_LIMITATIONS")
            self.assertFalse(result["fail_reasons"])
            self.assertTrue(result["limitations"])

    def test_direct_main_write_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root, "git push origin HEAD:main")
            result = evaluate(root)
            self.assertIn("DIRECT_MAIN_WRITE", result["fail_reasons"])
            self.assertEqual(result["result"], "BLOCK")

    def test_unknown_push_branch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root, "git push origin HEAD:$TARGET")
            result = evaluate(root)
            self.assertIn("UNKNOWN_PUSH_TARGET", result["fail_reasons"])

    def test_indirect_main_push_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root, "python scripts/worker.py",
                           "import subprocess\nsubprocess.run(['git','push','origin','HEAD:main'])\n")
            result = evaluate(root)
            self.assertIn("REFERENCED_SCRIPT_MAIN_WRITE_CANDIDATE", result["fail_reasons"])
            self.assertGreater(result["indirect_main_write_candidates"], 0)

    def test_feature_branch_write_is_review_not_main_violation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root, "python scripts/worker.py",
                           "import subprocess\nsubprocess.run(['git','push','origin','HEAD:refs/heads/feature/test'])\n")
            result = evaluate(root)
            self.assertEqual(result["result"], "PASS_WITH_REVIEW_LIMITATIONS")
            self.assertEqual(result["indirect_main_write_candidates"], 0)

    def test_missing_workflow_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                evaluate(Path(td))


if __name__ == "__main__":
    unittest.main()
