import hashlib
import tempfile
import unittest
from pathlib import Path
from automation_policy.research_handoff import inspect

class HandoffTests(unittest.TestCase):
    def test_missing_data_blocked(self):
        self.assertEqual(inspect(Path("/nonexistent/research.tsv"),"a"*64)["state"],"BLOCKED_EXTERNAL")
    def test_checksum_rejection(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"test.tsv"
            p.write_text("gene\tancestry\tsource_url\nIDO1\tEUR\tfile://a\n")
            self.assertEqual(inspect(p,"0"*64)["reason"],"CHECKSUM_MISMATCH")
    def test_genuine_rows_not_analysed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"test.tsv"
            p.write_text("gene\tancestry\tsource_url\nIDO1\tEUR\tfile://a\nIDO1\tEAS\tfile://b\n")
            result=inspect(p,hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(result["paired_genes"],["IDO1"])
            self.assertEqual(result["state"],"INPUT_VALIDATED")
            self.assertFalse(result["analysis_executed"])
