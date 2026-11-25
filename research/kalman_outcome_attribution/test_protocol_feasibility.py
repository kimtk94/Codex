import unittest
import pandas as pd
from protocol_feasibility import compare, bear_episodes, rolling_feasibility


class ProtocolFeasibilityContracts(unittest.TestCase):
    def test_equal_date_not_trade_weighting(self):
        g=pd.DataFrame({"signal_date":["2024-01-02"]*4+["2024-01-03"]*2,
            "qualifies":[True,True,True,False,True,False],
            "net_return":[.1,.1,.1,0.,-.1,0.]})
        r=compare(g)
        self.assertEqual(r["matched_dates"],2)
        self.assertAlmostEqual(r["matched_date_mean_difference"],0.)
        self.assertAlmostEqual(r["qualifying_mean"],.05)

    def test_missing_complement_is_not_a_comparison(self):
        g=pd.DataFrame({"signal_date":["2024-01-02"],"qualifies":[True],"net_return":[.1]})
        r=compare(g)
        self.assertEqual(r["matched_dates"],0)
        self.assertIsNone(r["matched_date_mean_difference"])
        self.assertIsNone(r["equal_date_group_difference"])

    def test_rolling_windows_require_complete_episode_boundaries(self):
        cal=["2024-01-02","2024-01-03","2024-01-04","2024-01-05","2024-01-08"]
        ctx=pd.DataFrame({"regime_lagged":["BULL","BEAR","BEAR","BEAR","BULL"]},index=cal)
        ids,episodes=bear_episodes(ctx)
        b=pd.DataFrame({"signal_date":cal[1:4],"qualifies":[True,False,True],
            "net_return":[.02,-.03,.01],"episode":ids.loc[cal[1:4]].to_numpy()})
        a=b.iloc[:0].copy()
        r=rolling_feasibility(a,b,cal,2)
        self.assertEqual(r["windows"],4)
        self.assertEqual(r["metric_maxima"]["bear_matched_complete_episodes"],0)
        r=rolling_feasibility(a,b,cal,3)
        self.assertEqual(r["metric_maxima"]["bear_matched_complete_episodes"],1)
        self.assertEqual(r["h1_candidate_minimum_pass_windows"],0)
        self.assertEqual(r["h2_candidate_minimum_pass_windows"],0)


if __name__=="__main__":
    unittest.main()
