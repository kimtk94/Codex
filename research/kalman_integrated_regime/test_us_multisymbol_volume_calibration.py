"""Deterministic contracts for unweighted vs class-balanced probability controls."""
import unittest

import numpy as np

from research.kalman_integrated_regime.test_us_multisymbol_volume_screen import synthetic_daily
from research.kalman_integrated_regime.us_multisymbol_volume_screen import matched_cohorts
from research.kalman_integrated_regime.us_multisymbol_volume_calibration import (
    ARMS, calibrate_annual, reliability,
)


class MultiTickerProbabilityContracts(unittest.TestCase):
    def test_reliability_reconciles_samples(self):
        y=np.array([0,1,0,1,1,0,1,0])
        p=np.array([.1,.9,.2,.8,.6,.4,.95,.05])
        r=reliability(y,p,bins=5)
        self.assertEqual(sum(x["count"] for x in r["reliability_bins"]),len(y))
        self.assertLess(r["expected_calibration_error"],.4)

    def test_unweighted_vs_balanced_models_are_separate(self):
        self.assertIsNone(ARMS["P_unweighted"][1])
        self.assertEqual(ARMS["P_balanced"][1],"balanced")
        self.assertEqual(len(ARMS["V_unweighted"][0]),5)
        self.assertEqual(len(ARMS["P_unweighted"][0]),3)

    def test_training_exit_purged_jan_oct_and_baseline(self):
        d=synthetic_daily()
        for year in (2025,2026):
            train,test=matched_cohorts(d,year)
            report=calibrate_annual(train,test,year,bootstrap_reps=100)
            self.assertLess(report["train_last_known_target_exit"],f"{year}-01-01")
            self.assertGreater(report["test_matched_jan_oct"],120)
            self.assertLessEqual(int(report["test_window"][1][5:7]),10)
            self.assertEqual(set(report["targets"]),{"direction_up","next_session_large_move"})
            for target,rec in report["targets"].items():
                self.assertIn("constant_train_prevalence",rec["scores"])
                self.assertIn("V_unweighted",rec["scores"])
                self.assertIn("V_balanced",rec["scores"])
                self.assertEqual(rec["scores"]["constant_train_prevalence"]["mean_prediction"],
                                 rec["train_label_prevalence"])
                self.assertFalse(rec["not_live_approved"] is False)
                self.assertEqual(
                    rec["unweighted_volume_vs_price_5day_block_95pct"]["brier"]["valid_replicates"],
                    100)

    def test_future_label_modification_cannot_change_training_prevalence(self):
        d=synthetic_daily()
        train,test=matched_cohorts(d,2025)
        r1=calibrate_annual(train,test,2025,bootstrap_reps=100)
        d2=d.copy()
        d2.loc[d2.date_ny.dt.year.eq(2025),"next_session_rth_return"]=.05
        train2,test2=matched_cohorts(d2,2025)
        # 2025 labels have changed, but the 2024 cutoff and prevalence must not.
        self.assertAlmostEqual(
            r1["targets"]["next_session_large_move"]["training_only_large_move_cutoff"],
            float(np.quantile(abs(train2.next_session_rth_return.astype(float)),.75)),
            places=7)
        self.assertEqual(len(train),len(train2))


if __name__=="__main__":
    unittest.main()
