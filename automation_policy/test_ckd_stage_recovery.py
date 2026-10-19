import unittest
from automation_policy.ckd_stage_recovery import FILES
class RecoveryContractTests(unittest.TestCase):
    def test_required_outputs_are_explicit(self):
        self.assertEqual(len(FILES),8)
        self.assertIn("STAGE2C_SUSIE_DEFAULT.tsv",FILES)
        self.assertIn("STAGE3B_INTEGRATED_EVIDENCE.tsv",FILES)
