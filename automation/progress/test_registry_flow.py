import json
import unittest
from gate_gap_report import gap_rows
from acceptance_registry import verify

MANIFEST={"schema_version":1,"gates":{"ONE":{"tasks":["A01"],"required":["run_url"]}}}
TASKS={"A01"}

class RegistryIntegrationTest(unittest.TestCase):
    def test_accepted_record_changes_gap_output(self):
        entry={"gate_id":"ONE","decision":"ACCEPTED","reviewer":"reviewer",
               "reviewed_at":"2026-10-26T20:00:00+09:00",
               "evidence":{"run_url":"https://github.com/example/actions/runs/1"}}
        registry={"schema_version":1,"records":{"A01":entry}}
        self.assertEqual("ACCEPTED",verify(registry,MANIFEST,TASKS)[0]["state"])
        self.assertEqual(0,gap_rows(MANIFEST,registry["records"])[0]["missing_task_count"])
        self.assertEqual(1,gap_rows(MANIFEST,{})[0]["missing_task_count"])
    def test_invalid_registry_never_publishes_approval(self):
        entry={"gate_id":"ONE","decision":"ACCEPTED","reviewer":"reviewer",
               "reviewed_at":"2026-10-26T20:00:00+09:00","evidence":{}}
        with self.assertRaises(ValueError):
            verify({"schema_version":1,"records":{"A01":entry}},MANIFEST,TASKS)

if __name__=="__main__":
    unittest.main()
