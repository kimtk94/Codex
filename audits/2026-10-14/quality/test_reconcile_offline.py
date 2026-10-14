import unittest
from reconcile_offline import reconcile

class TestReconcile(unittest.TestCase):
    def setUp(self):
        self.mirror=[{"symbol":"LRCX","state":"OPEN","remaining_quantity":"0.049034"}]
    def test_no_broker(self):
        self.assertEqual(reconcile(self.mirror,None)["status"],"UNKNOWN")
    def test_missing_orders(self):
        self.assertEqual(reconcile(self.mirror,{"holdings":[{"symbol":"LRCX","quantity":"0.049034"}]})["status"],"UNKNOWN")
    def test_pass(self):
        self.assertEqual(reconcile(self.mirror,{"holdings":[{"symbol":"LRCX","quantity":"0.049034"}],"open_orders":[]})["status"],"PASS")
    def test_mismatch(self):
        self.assertEqual(reconcile(self.mirror,{"holdings":[{"symbol":"LRCX","quantity":"0.04"}],"open_orders":[]})["status"],"MISMATCH")

if __name__=="__main__":unittest.main()
