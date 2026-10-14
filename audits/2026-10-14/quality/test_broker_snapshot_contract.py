import unittest
from broker_snapshot_contract import validate
class SnapshotContract(unittest.TestCase):
 def test_valid(self):
  self.assertEqual(validate({"captured_at":"2026-10-14T12:00:00Z","holdings":[{"symbol":"LRCX","quantity":"0.049034"}],"open_orders":[]}),[])
 def test_missing_capture(self):
  self.assertIn("INVALID_CAPTURE_TIME",validate({"holdings":[],"open_orders":[]}))
 def test_missing_orders(self):
  self.assertIn("OPEN_ORDERS_NOT_LIST",validate({"captured_at":"2026-10-14T12:00:00Z","holdings":[]}))
 def test_bad_holding(self):
  self.assertIn("INVALID_HOLDING",validate({"captured_at":"2026-10-14T12:00:00Z","holdings":[{"symbol":"LRCX","quantity":"bad"}],"open_orders":[]}))
if __name__=="__main__": unittest.main()
