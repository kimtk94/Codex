import json
import tempfile
import unittest
from pathlib import Path
from automation_policy.discover_is import discover

class DiscoveryTests(unittest.TestCase):
    def test_absent_inputs_are_not_successful_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            report=discover(p/"missing",p/"not_source",p/"out")
            self.assertTrue(report["missing_inputs"])
            self.assertEqual(report["entries"],[])
            self.assertFalse(report["analysis_mr_performed"])

    def test_missing_sidecar_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"inputs").mkdir()
            (p/"inputs"/"sample.tsv").write_text("gene\tancestry\tsource_url\n")
            report=discover(p/"inputs",p/"none",p/"out")
            self.assertEqual(report["entries"][0]["reason"],"missing_checksum_sidecar")
