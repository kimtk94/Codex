"""No-lookahead and paired bootstrap unit contracts for 5 US symbols."""
import unittest

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.test_us_multisymbol_volume_screen import synthetic_daily
from research.kalman_integrated_regime.us_multisymbol_volume_screen import matched_cohorts
from research.kalman_integrated_regime.us_multisymbol_volume_robustness import (
    paired_block_bootstrap, matched_months, score,
)


class MultiSymbolRobustnessContracts(unittest.TestCase):
    def test_matched_jan_oct_and_no_future_label_train(self):
        d=synthetic_daily()
        for year in (2025,2026):
            train,test=matched_cohorts(d,year)
            record=matched_months(year,train,test,bootstrap_reps=100)
            self.assertEqual(record["train_sessions"],len(train))
            self.assertLess(record["test_jan_oct_sessions"],len(test)+1)
            self.assertTrue(record["test_last"][:4]==str(year))
            self.assertLessEqual(int(record["test_last"][5:7]),10)
            self.assertTrue(record["last_prior_year_train_label"] < f"{year}-01-01")
            for target in ("direction_up","next_session_large_move"):
                self.assertTrue(record["outcomes"][target]["exploratory_many_comparisons"])
                self.assertFalse(record["outcomes"][target]["volume_inclusion_approved"])
                self.assertGreaterEqual(
                    record["outcomes"][target]["paired_five_session_block_bootstrap_95pct"]["brier"]["valid_replicates"],95)

    def test_bootstrap_fixed_seed_and_paired(self):
        rng=np.random.default_rng(145)
        y=np.array([0,1]*75)
        p=rng.uniform(.3,.7,len(y))
        q=np.clip(.1+.8*y,.001,.999)
        r1=paired_block_bootstrap(y,p,q,repeats=100,seed=57)
        r2=paired_block_bootstrap(y,p,q,repeats=100,seed=57)
        self.assertEqual(r1,r2)
        self.assertLess(r1["brier"]["high"],0)
        self.assertGreater(r1["auc"]["low"],0)
        with self.assertRaisesRegex(ValueError,"BOOTSTRAP_UNPAIRED"):
            paired_block_bootstrap(y,p,q[:-1],repeats=100)

    def test_no_skill_is_train_base_rate_not_test(self):
        d=synthetic_daily()
        train,test=matched_cohorts(d,2025)
        record=matched_months(2025,train,test,bootstrap_reps=100)
        x=record["outcomes"]["next_session_large_move"]
        self.assertTrue(0<x["train_label_positive_rate"]<1)
        self.assertTrue(0<x["no_skill_train_prevalence"]["brier"]<1)
        self.assertAlmostEqual(score([0,1],[.5,.5])["brier"],.25)


if __name__=="__main__":
    unittest.main()
