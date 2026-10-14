import unittest
from reconcile_offline import reconcile

class TestReconcile(unittest.TestCase):
    def setUp(self):
        self.mirror=[{"symbol":"LRCX","state":"OPEN","remaining_quantity":"0.049034"}]
        self.broker={"captured_at":"2026-10-14T12:30:00Z","holdings":[{"symbol":"LRCX","quantity":"0.049034"}],"open_orders":[]}
    def test_no_broker(self):
        self.assertEqual(reconcile(self.mirror,None)["status"],"UNKNOWN")
    def test_missing_orders(self):
        self.assertEqual(reconcile(self.mirror,{"captured_at":"2026-10-14T12:30:00Z","holdings":[]})["status"],"UNKNOWN")
    def test_holdings_match_not_full_pass(self):
        self.assertEqual(reconcile(self.mirror,self.broker)["status"],"HOLDINGS_MATCH")
    def test_submitted_lifecycle_pending(self):
        self.assertEqual(reconcile(self.mirror,self.broker,expected_submitted=21)["status"],"PARTIAL")
    def test_mismatch(self):
        b={**self.broker,"holdings":[{"symbol":"LRCX","quantity":"0.04"}]}
        self.assertEqual(reconcile(self.mirror,b)["status"],"MISMATCH")
    def test_duplicate_broker_holding(self):
        b={**self.broker,"holdings":self.broker["holdings"]*2}
        self.assertEqual(reconcile(self.mirror,b)["status"],"UNKNOWN")
    def test_duplicate_mirror_position(self):
        self.assertEqual(reconcile(self.mirror*2,self.broker)["status"],"UNKNOWN")
    def test_invalid_mirror_quantity(self):
        m=[{**self.mirror[0],"remaining_quantity":"NaN"}]
        self.assertEqual(reconcile(m,self.broker)["status"],"UNKNOWN")
    def test_stale_missing_capture_time(self):
        b={**self.broker,"captured_at":None}
        self.assertEqual(reconcile(self.mirror,b)["status"],"UNKNOWN")

if __name__=="__main__":unittest.main()
