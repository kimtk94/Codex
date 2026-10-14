import datetime as dt
import unittest
from quality_gate import evaluate

NOW=dt.datetime(2026,10,14,11,35,tzinfo=dt.timezone.utc)
BASE={"market":"US","status":"READY","generated_at":"2026-10-14T10:00:00Z",
      "data_as_of":"2026-10-14T09:00:00Z","stale_after":"2026-10-14T12:00:00Z"}

class QualityGateTest(unittest.TestCase):
    def test_fresh(self):
        self.assertTrue(evaluate(BASE,NOW)["quality_pass"])
    def test_stale(self):
        result=evaluate({**BASE,"stale_after":"2026-10-14T11:00:00Z"},NOW)
        self.assertFalse(result["quality_pass"])
        self.assertIn("READY_BUT_STALE",result["flags"])
    def test_created_expired(self):
        result=evaluate({**BASE,"stale_after":"2026-10-14T09:59:59Z"},NOW)
        self.assertIn("EXPIRED_AT_GENERATION",result["flags"])
    def test_future_data(self):
        result=evaluate({**BASE,"data_as_of":"2026-10-14T11:00:00Z"},NOW)
        self.assertIn("DATA_AFTER_GENERATION",result["flags"])
    def test_missing(self):
        result=evaluate({**BASE,"stale_after":None},NOW)
        self.assertEqual(result["freshness"],"UNKNOWN")
        self.assertFalse(result["quality_pass"])
    def test_status_not_ready(self):
        self.assertFalse(evaluate({**BASE,"status":"FAILED"},NOW)["quality_pass"])
    def test_bad_timezone(self):
        self.assertFalse(evaluate({**BASE,"generated_at":"2026-10-14T10:00:00"},NOW)["quality_pass"])

if __name__=="__main__":
    unittest.main()
