import unittest
from automation_policy.checkpoint import fingerprint,resume

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.spec={"steps":[{"id":"qc","action":"research.analysis_qc","needs":[]},
                            {"id":"docs","action":"research.docs_web_update","needs":["qc"]}]}
        self.commit="a"*40

    def test_without_prior_starts_at_qc(self):
        r=resume(self.spec,None,expected_commit=self.commit)
        self.assertEqual(r["next"],"qc")
        self.assertEqual(r["completed"],[])

    def test_forged_completed_is_never_trusted(self):
        prior={"version":1,"plan_sha256":fingerprint(self.spec),"source_commit":self.commit,
               "completed":["qc","docs"]}
        r=resume(self.spec,prior,expected_commit=self.commit)
        self.assertEqual(r["completed"],[])
        self.assertEqual(r["status"],"CHECKPOINT_METADATA_MATCH_ONLY")

    def test_changed_commit_resets(self):
        prior={"version":1,"plan_sha256":fingerprint(self.spec),"source_commit":"b"*40,
               "completed":["qc"]}
        self.assertEqual(resume(self.spec,prior,expected_commit=self.commit)["status"],"NO_TRUSTED_CHECKPOINT")

    def test_modified_plan_resets(self):
        prior={"version":1,"plan_sha256":"f"*64,"source_commit":self.commit,"completed":["qc"]}
        self.assertEqual(resume(self.spec,prior,expected_commit=self.commit)["completed"],[])
