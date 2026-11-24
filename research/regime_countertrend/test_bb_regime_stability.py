import unittest
import pandas as pd
from research.regime_countertrend.bb_regime_stability import audit

class BBStabilityTests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame([
           {"date":"2024-01-02","year":2024,"event":"UP_DIP","failed":True,"net_return":-.032,"bb_pct_b":.2},
           {"date":"2024-01-09","year":2024,"event":"UP_DIP","failed":False,"net_return":.028,"bb_pct_b":.8},
           {"date":"2025-01-02","year":2025,"event":"UP_DIP","failed":False,"net_return":.028,"bb_pct_b":.2},
           {"date":"2025-01-09","year":2025,"event":"UP_DIP","failed":True,"net_return":-.032,"bb_pct_b":.8}
        ])
    def test_direction_reversal_and_no_auto_promotion(self):
        table,meta=audit(self.fixture())
        self.assertTrue(meta["direction_reversed"])
        self.assertEqual(meta["status"],"HOLD")
        self.assertFalse(meta["promotion_allowed"])
        self.assertEqual(len(table),6)
    def test_no_future_leakage_to_development(self):
        d=self.fixture()
        before,_=audit(d)
        d.loc[d.year==2025,"failed"]=[True,False]
        after,_=audit(d)
        a=before[before.era=="DEVELOPMENT_PRE2025"].reset_index(drop=True)
        b=after[after.era=="DEVELOPMENT_PRE2025"].reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b)
    def test_bad_columns(self):
        with self.assertRaises(ValueError):
            audit(pd.DataFrame({"year":[2025]}))
if __name__=="__main__":unittest.main()
