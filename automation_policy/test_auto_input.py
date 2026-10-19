import tempfile
import unittest
from pathlib import Path
from automation_policy.auto_input import ingest

class AutoInputTests(unittest.TestCase):
    def test_missing_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            result=ingest(Path(d)/"missing",Path(d)/"out")
            self.assertEqual(result["state"],"BLOCKED_EXTERNAL")
            self.assertFalse(result["analysis_executed"])

    def test_invalid_manifest_does_not_claim_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"repo"
            p=root/"data"/"metadata"/"ukb_ppp_download_manifest.tsv"
            p.parent.mkdir(parents=True)
            p.write_text("incorrect\\theader\\n")
            result=ingest(root,Path(d)/"out")
            self.assertFalse(result["analysis_executed"])
            self.assertEqual(result["state"],"BLOCKED_EXTERNAL")
