import unittest
from acceptance_registry import verify
M={"schema_version":1,"gates":{"G":{"tasks":["A01"],"required":["run_url","counts"]}}}
T={"A01"}
class AcceptanceRegistryTest(unittest.TestCase):
    def test_empty_is_unverified(self):
        self.assertEqual("NOT_VERIFIED",verify({"schema_version":1,"records":{}},M,T)[0]["state"])
    def test_explicit_complete(self):
        r={"schema_version":1,"records":{"A01":{"gate_id":"G","decision":"ACCEPTED",
        "reviewer":"test-reviewer","reviewed_at":"2026-10-26T12:00:00+09:00",
        "evidence":{"run_url":"https://example.com/run","counts":"reconciled"}}}}
        self.assertEqual("ACCEPTED",verify(r,M,T)[0]["state"])
    def test_missing_evidence_is_rejected(self):
        r={"schema_version":1,"records":{"A01":{"gate_id":"G","decision":"ACCEPTED",
        "reviewer":"test-reviewer","reviewed_at":"2026-10-26T12:00:00+09:00","evidence":{}}}}
        with self.assertRaises(ValueError): verify(r,M,T)
    def test_timezone_required(self):
        r={"schema_version":1,"records":{"A01":{"gate_id":"G","decision":"REJECTED",
        "reviewer":"test-reviewer","reviewed_at":"2026-10-26T12:00:00"}}}
        with self.assertRaises(ValueError): verify(r,M,T)
if __name__=="__main__": unittest.main()
