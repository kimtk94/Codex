import unittest
import numpy as np
import pandas as pd
from market_relative import BASE, INTER, CORE, feature_panel, split, daily_scores


class MarketRelativeContracts(unittest.TestCase):
    def fixture(self):
        dates = pd.bdate_range("2021-01-01", "2024-03-01")
        rng = np.random.default_rng(42)
        return {s: pd.Series(100*np.exp(np.cumsum(rng.normal(.0002,.01,len(dates)))),
                            index=dates)
                for s in CORE+["SPY","SMH","HYG","LQD","GLD"]}

    def test_causal_features_not_changed_by_future_closes(self):
        prices = self.fixture()
        cut = pd.Timestamp("2023-10-02")
        panel, _ = feature_panel(prices)
        changed = {s: c.where(c.index <= cut, c*2) for s,c in prices.items()}
        p2, _ = feature_panel(changed)
        cols = ["symbol","signal_date",*BASE,*INTER,"momentum_regime","sector_regime"]
        a = panel.loc[panel.signal_date.le(cut),cols].reset_index(drop=True)
        b = p2.loc[p2.signal_date.le(cut),cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b)
        # Future outcomes may change; they are not included in the predictor columns.
        self.assertNotIn("relative_return", BASE+INTER)
        self.assertNotIn("exit_date", BASE+INTER)

    def test_relative_label_and_four_session_exit_purge(self):
        prices = self.fixture()
        p, cal = feature_panel(prices)
        a = p.iloc[-100]
        i = cal.get_loc(a.signal_date)
        relative = prices[a.symbol]/prices["SPY"]
        self.assertEqual(a.exit_date, cal[i+4])
        self.assertAlmostEqual(a.relative_return, relative.iloc[i+4]/relative.iloc[i]-1)
        tr,te,cut = split(p,cal,2024)
        self.assertTrue(tr.exit_date.lt(cut).all())
        self.assertTrue(te.signal_date.dt.year.eq(2024).all())
        self.assertEqual(cut,cal[cal.get_loc(te.signal_date.min())-4])

    def test_rank_ties_neutral_and_deterministic(self):
        p = pd.DataFrame({"signal_date":pd.Timestamp("2024-01-02"),
                          "momentum_regime":"SIDEWAYS","relative_return":[1.,2.,3.,4.,5.,6.],
                          "CONST":0.,"PERFECT":[1.,2.,3.,4.,5.,6.]})
        d = daily_scores(p,["CONST","PERFECT"]).set_index("method")
        self.assertTrue(pd.isna(d.loc["CONST","rank_ic"]))
        self.assertEqual(d.loc["CONST","spread"],0.)
        self.assertAlmostEqual(d.loc["PERFECT","rank_ic"],1.)
        self.assertAlmostEqual(d.loc["PERFECT","spread"],3.)
        q = daily_scores(p.sample(frac=1,random_state=42),["CONST","PERFECT"]).set_index("method")
        pd.testing.assert_frame_equal(d,q)


if __name__=="__main__":
    unittest.main()
