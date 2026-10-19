import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from automation_policy.unified_research import run

class UnifiedResearchTests(unittest.TestCase):
    def test_missing_manifest_blocks_science(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "research"
            source.mkdir()
            out = Path(tmp) / "out"
            with patch("automation_policy.unified_research.subprocess.run") as proc:
                proc.return_value.returncode = 0
                proc.return_value.stdout = "a"*40 + chr(10)
                report = run(source,out)
            self.assertEqual(report["completed_stage_count"],1)
            self.assertFalse(report["real_analysis"]["mr"])
            self.assertTrue(all(s["state"]=="BLOCKED_EXTERNAL" for s in report["stages"][1:]))
            self.assertTrue((out/"research-harness-status.md").exists())

    def test_invalid_checkout_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run(Path(tmp),Path(tmp)/"out")
