import unittest
import numpy as np
import pandas as pd

from kalman_ablation import causal_features, split, trades, KALMAN, EMA


class KalmanAblationContracts(unittest.TestCase):
    def close(self):
        rng=np.random.default_rng(42)
        return pd.Series(100*np.exp(np.cumsum(rng.normal(.0003,.02,260))),
                         index=pd.date_range("2024-01-01",periods=260,freq="B"))

    def test_causal_filter_and_ema_ignore_future_observations(self):
        c=self.close();cut=c.index[140]
        full=causal_features(c)
        changed=c.copy();changed.loc[changed.index>cut]*=20
        pd.testing.assert_frame_equal(full.loc[:cut],causal_features(changed).loc[:cut])
        pd.testing.assert_frame_equal(full.loc[:cut],causal_features(c.loc[:cut]))
        self.assertTrue(full.iloc[:60].isna().all().all())
        self.assertTrue(full.iloc[60:].notna().all().all())

    def test_scale_invariant_log_state_features(self):
        c=self.close()
        pd.testing.assert_frame_equal(causal_features(c),causal_features(c*17),
                                      check_exact=False,rtol=1e-9,atol=1e-11)
        self.assertEqual(list(causal_features(c).columns),KALMAN+EMA)
        bad=c.copy();bad.iloc[100]=np.nan
        with self.assertRaisesRegex(ValueError,"INVALID_CLOSE_SERIES"):
            causal_features(bad)

    def test_training_label_must_exit_before_test_year(self):
        frame=pd.DataFrame({"exit_date":pd.to_datetime(["2024-12-31","2025-01-03","2025-01-08"])},
                           index=pd.to_datetime(["2024-12-24","2024-12-30","2025-01-02"]))
        tr,te=split(frame,2025)
        self.assertEqual(len(tr),1);self.assertEqual(len(te),1)
        self.assertTrue(tr.exit_date.lt(pd.Timestamp("2025-01-01")).all())

    def test_fixed_candidate_threshold_and_no_overlap(self):
        frame=pd.DataFrame({"symbol":["SPY"]*4,
            "signal_date":pd.to_datetime(["2025-01-02","2025-01-03","2025-01-09","2025-01-10"]),
            "exit_date":pd.to_datetime(["2025-01-08","2025-01-09","2025-01-15","2025-01-16"]),
            "score":[.6,.99,.59,.61],"net_return":[.01,-.1,.02,-.06],
            "win":[1,0,1,0],"severe":[0,1,0,1],"year":[2025]*4})
        chosen,summary=trades(frame,"score")
        self.assertEqual(summary["n"],2)
        self.assertEqual(chosen.signal_date.tolist(),list(pd.to_datetime(["2025-01-02","2025-01-10"])))
        self.assertAlmostEqual(summary["mean_net"],-.025)


if __name__=="__main__":
    unittest.main()
