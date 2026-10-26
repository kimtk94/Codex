import unittest
from publish_gate_gaps import prepare,EXPECTED
class GateSheetTests(unittest.TestCase):
    def test_exact_order(self):
        x=[{"gate_id":i,"missing_task_count":2,"missing_reasons":["NO_SIGNED_TASK_RECORD"]} for i in EXPECTED]
        self.assertEqual(13,len(prepare(x,EXPECTED)))
        with self.assertRaises(ValueError): prepare(x,list(reversed(EXPECTED)))
if __name__=="__main__": unittest.main()
