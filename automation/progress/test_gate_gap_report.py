import unittest
from gate_gap_report import gap_rows
class GateGapTest(unittest.TestCase):
    def test_missing_is_visible(self):
        m={"gates":{"G":{"tasks":["A01","A02"],"required":["run_url"]}}}
        report=gap_rows(m)
        self.assertEqual(["A01","A02"],report[0]["missing_task_ids"])
        self.assertEqual(["NO_SIGNED_TASK_RECORD"],report[0]["missing_reasons"])
    def test_no_private_evidence_in_gap_output(self):
        m={"gates":{"G":{"tasks":["A01"],"required":["run_url"]}}}
        report=gap_rows(m,{"A01":{"gate_id":"G","decision":"ACCEPTED","reviewer":"r","reviewed_at":"now","evidence":{"run_url":"private"}}})
        self.assertNotIn("private",repr(report))
if __name__=="__main__":
    unittest.main()
