import unittest
from v25_research import RollingGrid,evaluate
from kalman_grid_v23 import D
class Tests(unittest.TestCase):
    def test_cancel_recenter_reservation(self):
        g=RollingGrid('100');ids=list(g.buys.values());g.recenter('105')
        self.assertTrue(all(g.ledger.orders[i].state.value=='CANCELLED' for i in ids))
        self.assertTrue(g.ledger.audit())
    def test_preserves_inventory_and_sell(self):
        g=RollingGrid('100');g.update('99','t')
        asset=g.ledger.asset;sells=dict(g.sells)
        self.assertGreater(asset,0)
        g.recenter('102')
        self.assertEqual(asset,g.ledger.asset)
        self.assertEqual(sells,g.sells)
    def test_no_phantom_profit_on_flat_market(self):
        x=evaluate([(str(i),'100') for i in range(20)],anchor_every=5)
        self.assertEqual(x['fills'],0)
        self.assertEqual(x['return_pct'],0)
    def test_basic_realized_rebalance(self):
        x=evaluate([('0','100'),('1','99'),('2','100'),('3','101')],anchor_every=0)
        self.assertGreaterEqual(x['fills'],1)
        self.assertGreaterEqual(x['cash'],0)
if __name__=='__main__':unittest.main()
