import unittest
import numpy as np
import pandas as pd
from regime_feature_slices import market_context, describe, COLS

class RegimeSliceContracts(unittest.TestCase):
    def test_market_context_is_lagged(self):
        c=pd.Series(np.linspace(100,120,60),index=pd.date_range("2025-01-01",periods=60,freq="B"))
        prices={k:c.copy() for k in ("SPY","HYG","LQD","TLT")}
        a=market_context(prices)
        for k in prices:
            prices[k].iloc[-1]*=2
        pd.testing.assert_frame_equal(a,market_context(prices))
    def test_warmup_not_classified(self):
        c=pd.Series(np.arange(1.,31.),index=pd.date_range("2025-01-01",periods=30,freq="B"))
        a=market_context({k:c for k in ("SPY","HYG","LQD","TLT")})
        self.assertEqual(a.index[0],c.index[21])
    def test_sparse_and_single_class_auc(self):
        f=pd.DataFrame({"net_return":[.01,.02],"signal_date":pd.date_range("2025-01-01",periods=2),
                        **{k:[1.,2.] for k in COLS}})
        r=describe(f)
        self.assertTrue(r["sparse_evidence"])
        self.assertTrue(all(v is None for v in r["severe_auc_descriptive"].values()))
        f.loc[1,"net_return"]=-.05
        r=describe(f)
        self.assertEqual(r["severe"],1)
        self.assertEqual(r["severe_auc_descriptive"]["vol20"],1)
        self.assertTrue(r["sparse_evidence"])
