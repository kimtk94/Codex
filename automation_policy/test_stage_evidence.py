import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from automation_policy.stage_evidence import verify

class StageEvidenceTests(unittest.TestCase):
    def test_verified_artifact_not_scientific_qc(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"result.txt").write_text("a result")
            h=hashlib.sha256((root/"result.txt").read_bytes()).hexdigest()
            m=root/"manifest.json"
            m.write_text(json.dumps({"version":1,"stages":[{"stage":"mr","source_commit":"a"*40,"outputs":[{"path":"result.txt","sha256":h}]}]}))
            result=verify(root,m)
            self.assertEqual(result["stage_integrity"]["mr"],"ARTIFACT_INTEGRITY_VERIFIED")
            self.assertFalse(result["scientific_qc_verified"])
    def test_missing_file_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=root/"manifest.json"
            m.write_text(json.dumps({"version":1,"stages":[{"stage":"mr","source_commit":"a"*40,"outputs":[{"path":"missing","sha256":"a"*64}]}]}))
            self.assertEqual(verify(root,m)["stage_integrity"]["mr"],"BLOCKED_UNVERIFIED")
