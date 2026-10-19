import json
import tempfile
import unittest
from pathlib import Path
from automation_policy.executors import run_qc, create_qc_report

class ExecutorsTests(unittest.TestCase):
    def test_real_plan_integrity_qc_and_report(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            result = run_qc(path)
            self.assertTrue(result["valid"])
            self.assertTrue(create_qc_report(path)["verified_input"])
            self.assertIn("does not represent", (path / "qc-report.md").read_text())

    def test_report_fails_without_qc(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                create_qc_report(Path(td))

    def test_report_fails_invalid_qc(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "qc-evidence.json").write_text(json.dumps({"valid": False}))
            with self.assertRaises(ValueError):
                create_qc_report(path)
