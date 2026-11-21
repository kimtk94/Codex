import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.sector_price_sources_v3 import manifest_load
from research.regime_countertrend.peer_macro_v4 import (
    MACRO_ETFS, MACRO_COLS, PEER_RAW_THRESHOLD, PEER_RESIDUAL_THRESHOLD,
    discover_residual_peers,macro_history,MacroPCA,compare_with_v3
)

MANIFEST="research/regime_countertrend/universe_sector_v3.json"

class PeerMacroV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=manifest_load(MANIFEST)
    def sample_prices(self):
        rng=np.random.default_rng(702)
        dates=pd.bdate_range("2022-01-03",periods=900).strftime("%Y-%m-%d")
        t=np.arange(len(dates))
        market=rng.normal(0,.01,len(t))
        semiconductor=rng.normal(0,.013,len(t))
        prices={}
        def frame(ret):
            return pd.DataFrame({"date":dates,
                   "close":100*np.exp(np.cumsum(ret))})
        prices["QQQ"]=frame(market)
        for ticker in ("AMD","NVDA","MU"):
            ret=market*.85+semiconductor*(1.0 if ticker!="NVDA" else 1.1)
            ret+=rng.normal(0,.002,len(t))
            prices[ticker]=frame(ret)
        prices["AAPL"]=frame(market*.8+rng.normal(0,.012,len(t)))
        for etf in MACRO_ETFS:
            prices[etf]=frame(market*.4+rng.normal(0,.004,len(t)))
        return prices
    def test_residual_peers_remove_market_effect(self):
        data=self.sample_prices()
        peers,edges=discover_residual_peers(data,self.registry,2025)
        self.assertIn("NVDA",peers["AMD"])
        self.assertIn("MU",peers["AMD"])
        self.assertNotIn("AAPL",peers["AMD"])
        self.assertTrue((edges.prior_date_end<"2025-01-01").all())
        self.assertTrue((edges.loc[edges.pair_eligible,"residual_corr"]>=PEER_RESIDUAL_THRESHOLD).all())
        self.assertTrue((edges.loc[edges.pair_eligible,"raw_corr"]>=PEER_RAW_THRESHOLD).all())
    def test_future_close_changes_cannot_change_fitted_peer_edges(self):
        data=self.sample_prices()
        peers,edges=discover_residual_peers(data,self.registry,2025)
        later={k:v.copy() for k,v in data.items()}
        later["NVDA"].loc[later["NVDA"].date>="2025-01-01","close"]*=17
        later_peers,later_edges=discover_residual_peers(later,self.registry,2025)
        self.assertEqual(peers,later_peers)
        pd.testing.assert_frame_equal(edges,later_edges)
    def test_macro_pca_takes_etf_factors_only_and_no_future(self):
        prices=self.sample_prices()
        features=macro_history(prices)
        self.assertEqual(set(MACRO_COLS),set(features)-{"date"})
        train=features[features.date<"2025-01-01"].dropna()
        ref=MacroPCA().fit(train)
        changed=features.copy()
        changed.loc[changed.date>="2025-01-01","SMH_minus_SPY"]+=999.
        other=MacroPCA().fit(changed[changed.date<"2025-01-01"].dropna())
        np.testing.assert_allclose(ref.transform(train.tail(4)),
            other.transform(train.tail(4)),rtol=1e-12)
        self.assertEqual(ref.transform(train.tail(5)).shape,(5,3))
    def test_missing_etf_daily_values_are_hold(self):
        prices=self.sample_prices()
        del prices["GLD"]
        with self.assertRaises(ValueError):
            macro_history(prices)
    def test_model_comparison_rejects_nonidentical_returns(self):
        p=pd.DataFrame([{"date":"2025-02-04","symbol":"AMD","year":2025,
             "industry":"SEMICONDUCTORS","event":"SIDE_DIP","net_20bp":-.032,
             "macro_market_selected":False,"macro_peer_selected":True}])
        old=pd.DataFrame([{"date":"2025-02-04","symbol":"AMD","year":2025,
             "net_20bp":.028,"global_selected":True,"hierarchical_selected":False}])
        with self.assertRaises(ValueError):
            compare_with_v3(p,old)
    def test_compare_same_trades(self):
        p=pd.DataFrame([{"date":"2025-02-04","symbol":"AMD","year":2025,
             "industry":"SEMICONDUCTORS","event":"SIDE_DIP","net_20bp":-.032,
             "macro_market_selected":False,"macro_peer_selected":True}])
        old=pd.DataFrame([{"date":"2025-02-04","symbol":"AMD","year":2025,
             "net_20bp":-.032,"global_selected":True,"hierarchical_selected":False}])
        m,ind=compare_with_v3(p,old)
        self.assertEqual(len(m),5)
        self.assertEqual(len(ind),4)
        self.assertFalse(m.empty)
if __name__=="__main__":
    unittest.main()
