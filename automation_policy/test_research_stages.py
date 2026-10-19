import unittest
from automation_policy.research_stages import assess

class StageTests(unittest.TestCase):
    def test_missing_data_blocks_all(self):
        report=assess({},set())
        self.assertTrue(all(s["state"]=="BLOCKED_EXTERNAL" for s in report["stages"]))
    def test_dependencies_must_be_verified(self):
        stages=assess({"mr_inputs":True},set())["stages"]
        self.assertEqual(stages[1]["state"],"BLOCKED_EXTERNAL")
    def test_ready_is_not_execution(self):
        stages=assess({"pqtl_manifest":True},set())["stages"]
        self.assertEqual(stages[0]["state"],"READY_FOR_VERIFIED_EXECUTOR")
        self.assertFalse(stages[0]["analysis_executed"])
    def test_koges_block_without_access(self):
        stages=assess({"kidney_annotation":True},set())["stages"]
        self.assertIn("koges_controlled_access",stages[-1]["missing_inputs"])
