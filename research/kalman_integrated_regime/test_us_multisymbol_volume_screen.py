"""Deterministic, no-lookahead contracts for five-stock volume ablation."""
import unittest

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_multisymbol_volume_screen import (
    PRICE, VOLUME, ARMS, matched_cohorts, model_quality,
)


def synthetic_daily():
    dates=pd.bdate_range("2024-01-02","2026-10-29")
    rng=np.random.default_rng(20261031)
    n=len(dates)
    f=pd.DataFrame({
        "date_ny":dates,
        "complete_rth":True,
        "price_r5":rng.normal(0,.03,n),
        "price_r20":rng.normal(0,.06,n),
        "price_logvol20":rng.uniform(.006,.045,n),
        "rvol20":rng.lognormal(0,.4,n),
        "volume_z20":rng.normal(0,1,n),
        "next_session_date":pd.Series(dates).shift(-1),
        "next_session_rth_return":rng.normal(.0001,.017,n)
    })
    f.loc[n-1,["next_session_date","next_session_rth_return"]]=pd.NA
    return f


class ScreenContracts(unittest.TestCase):
    def test_purged_unseen_next_session_label(self):
        d=synthetic_daily()
        for year in (2025,2026):
            train,test=matched_cohorts(d,year)
            self.assertLess(train.next_session_date.max(),pd.Timestamp(f"{year}-01-01"))
            self.assertTrue(test.date_ny.dt.year.eq(year).all())
            self.assertTrue(test.next_session_date.dt.year.eq(year).all())
            self.assertFalse(set(train.date_ny)&set(test.date_ny))
            self.assertGreater(len(train),100)
            self.assertGreater(len(test),70)

    def test_four_yearly_tasks_have_locked_cohorts(self):
        d=synthetic_daily()
        tr,te=matched_cohorts(d,2025)
        report=model_quality(tr,te,2025)
        self.assertEqual(set(report["models"]),{"direction_up","next_session_large_move"})
        self.assertEqual(ARMS["P_price_3"],PRICE)
        self.assertEqual(ARMS["V_price_volume_5"],PRICE+VOLUME)
        for target, rec in report["models"].items():
            self.assertEqual(rec["arms"]["P_price_3"]["n_features"],3)
            self.assertEqual(rec["arms"]["V_price_volume_5"]["n_features"],5)
            self.assertTrue(rec["same_train_test_dates"])
            for arm in rec["arms"].values():
                self.assertTrue(0<=arm["brier"]<=1)
                self.assertTrue(0<=arm["logloss"])
                self.assertTrue(0<=arm["auc"]<=1)

    def test_missing_rvol_removes_observation_from_both_arms(self):
        d=synthetic_daily()
        n=len(matched_cohorts(d,2025)[1])
        target=d.index[d.date_ny.eq(pd.Timestamp("2025-05-20"))][0]
        d.loc[target,"rvol20"]=np.nan
        self.assertEqual(len(matched_cohorts(d,2025)[1]),n-1)

    def test_future_outcome_does_not_change_train_fit_or_threshold(self):
        d=synthetic_daily()
        train,test=matched_cohorts(d,2025)
        result=model_quality(train,test,2025)
        modified=d.copy()
        modified.loc[modified.date_ny.dt.year.eq(2025),
                     "next_session_rth_return"]=0.45
        train2,test2=matched_cohorts(modified,2025)
        self.assertEqual(len(train),len(train2))
        self.assertAlmostEqual(
            result["models"]["next_session_large_move"]["train_magnitude_cutoff_abs_fraction"],
            model_quality(train2,test2,2025)["models"]["next_session_large_move"]["train_magnitude_cutoff_abs_fraction"]
        )

    def test_explicit_label_exit_purge(self):
        d=synthetic_daily()
        idx=d.index[d.date_ny.eq(pd.Timestamp("2024-12-31"))][0]
        d.loc[idx,"next_session_date"]=pd.Timestamp("2025-01-02")
        tr,te=matched_cohorts(d,2025)
        self.assertFalse((tr.date_ny==pd.Timestamp("2024-12-31")).any())


if __name__=="__main__":
    unittest.main()
