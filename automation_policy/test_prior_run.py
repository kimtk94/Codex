import unittest
from automation_policy.prior_run import inspect

class PreviousRunTests(unittest.TestCase):
    def setUp(self):
        self.run={"repository":{"full_name":"kimtk94/Codex"},"head_sha":"a"*40,
                  "head_branch":"main","workflow_id":389114094,"event":"schedule",
                  "status":"completed","conclusion":"success"}
        self.args={"repository":"kimtk94/Codex","head_sha":"a"*40,
                   "ref":"refs/heads/main","workflow_id":389114094}
    def test_metadata_matches_but_not_trusted_completion(self):
        v=inspect(self.run,**self.args)
        self.assertTrue(v["origin_ok"])
        self.assertFalse(v["trusted_completion"])
    def test_wrong_branch_denied(self):
        self.run["head_branch"]="untrusted"
        self.assertFalse(inspect(self.run,**self.args)["origin_ok"])
    def test_failed_run_denied(self):
        self.run["conclusion"]="failure"
        self.assertFalse(inspect(self.run,**self.args)["origin_ok"])
