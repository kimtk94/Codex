"""Four-arm QLD/QQQ relative-volume model: no leakage / locked cohort tests."""
import unittest

import numpy as np
import pandas as pd

from research.kalman_integrated_regime import run as base
from research.kalman_integrated_regime.volume_four_arm import (
    ARMS,VOLUME,common_eligible,paired_cohorts,compare_annual,
)


def synthetic_data():
    days=pd.bdate_range("2024-05-01","2025-06-30")
    rng=np.random.default_rng(145)
    names=list(dict.fromkeys(sum((v for v in ARMS.values()),[])))
    f=pd.DataFrame(rng.normal(size=(len(days),len(names))),
                   index=days,columns=names)
    # Ensure volume is strictly positive and macro VIX in a realistic scale.
    f["qqq_rvol20"]=np.exp(f["qqq_rvol20"]/5)
    f["qld_rvol20"]=np.exp(f["qld_rvol20"]/5)
    f["vix_lag1"]=20.0
    f["tnx_lag1"]=4.0
    events=[]
    for i,day in enumerate(days[:-6]):
        next_date=days[i+1]
        exit_date=days[i+2]
        events.append({"date":day,"entry_date":next_date,"exit_date":exit_date,
                       "positive":int(i%3!=0),
                       "net_return":.01 if i%3 else -.02})
    return f,pd.DataFrame(events),days


class VolumeAblationContracts(unittest.TestCase):
    def test_locked_four_arms_and_no_separate_cohort_optimism(self):
        f,events,days=synthetic_data()
        train,test=paired_cohorts(f,events,2025,min_train=80)
        self.assertGreater(len(train),80)
        self.assertGreater(len(test),30)
        self.assertTrue((train.exit_date < pd.Timestamp("2025-01-01")).all())
        self.assertEqual(len(ARMS),4)
        self.assertEqual([len(x) for x in ARMS.values()],[5,9,10,14])
        self.assertEqual(VOLUME,["qqq_rvol20","qld_rvol20",
                                 "qqq_volume_z20","qld_volume_z20"])
        self.assertFalse(set(train.date) & set(test.date))
        self.assertEqual(len(test),sum(events.date.dt.year==2025))

    def test_single_missing_volume_row_removes_day_from_all_arms(self):
        f,events,_=synthetic_data()
        date=events.loc[events.date.dt.year.eq(2025),"date"].iloc[7]
        before=len(paired_cohorts(f,events,2025)[1])
        f.loc[date,"qqq_rvol20"]=np.nan
        valid=common_eligible(f)
        self.assertFalse(valid.loc[date])
        self.assertEqual(len(paired_cohorts(f,events,2025)[1]),before-1)

    def test_late_training_label_is_purged(self):
        f,events,_=synthetic_data()
        idx=events.index[events.date.eq(pd.Timestamp("2024-12-31"))]
        if len(idx):
            events.loc[idx,"exit_date"]=pd.Timestamp("2025-01-02")
        train,_=paired_cohorts(f,events,2025,min_train=80)
        self.assertTrue((train.exit_date < pd.Timestamp("2025-01-01")).all())

    def test_missing_features_fail_closed(self):
        f,_,_=synthetic_data()
        with self.assertRaisesRegex(ValueError,"MISSING_ABLATION_FEATURES"):
            common_eligible(f.drop(columns=["qld_volume_z20"]))

    def test_identical_fixed_policy_from_model_comparison(self):
        f,events,days=synthetic_data()
        # Every session has a bar with high and low sufficiently far from open
        # to force an exit without consulting any future classifier feature.
        candles={}
        for d in days:
            candles[d]=pd.DataFrame([{
                "open":100.0,"high":104.0,"low":99.0,"close":103.0
            }])
        res=compare_annual(f,events,candles,2025)
        self.assertEqual(set(res["arms"]),set(ARMS))
        self.assertEqual(len(res["contrasts"]),2)
        self.assertTrue(res["identical_training_cohort"])
        self.assertTrue(res["identical_test_signal_cohort"])
        for record in res["arms"].values():
            self.assertEqual(record["test_labeled"],len(paired_cohorts(f,events,2025)[1]))
        self.assertEqual(res["fixed_execution_settings"]["tp"],base.TP)
        self.assertEqual(res["fixed_execution_settings"]["sl"],base.SL)


if __name__=="__main__":
    unittest.main()
