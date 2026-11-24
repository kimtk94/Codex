"""Research-only strict net 2.0 risk geometry and entry/opportunity tests."""
import unittest
import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_regime_rr_entry_gate import (
    entry_plan, simulate,
)
from research.kalman_integrated_regime.us_regime_rr2_feasibility import (
    POLICIES, analytical_atr_band, preentry_counters, MIN_NET_RR,
)


def candle():
    return pd.DataFrame([
        {"open":99.9,"high":100.1,"low":99.8,"close":100.},
        {"open":100.,"high":100.4,"low":99.8,"close":100.2}
    ])


class StrictGeometryContracts(unittest.TestCase):
    def test_analytic_feasibility_bands_derived_without_price_outcomes(self):
        base=analytical_atr_band(1.25,3.0)
        moderate=analytical_atr_band(1.0,2.5)
        tight=analytical_atr_band(.75,2.25)
        self.assertAlmostEqual(base["atr_over_entry_min"],.018)
        self.assertAlmostEqual(base["atr_over_entry_max"],.024)
        self.assertAlmostEqual(moderate["atr_over_entry_min"],.018)
        self.assertAlmostEqual(moderate["atr_over_entry_max"],.03)
        self.assertAlmostEqual(tight["atr_over_entry_min"],.012)
        self.assertAlmostEqual(tight["atr_over_entry_max"],round(.08/2.25,7))
        self.assertTrue(all(x["possible"] for x in (base,moderate,tight)))
        with self.assertRaisesRegex(ValueError,"IMPOSSIBLE_MULTIPLIERS_TO_PASS"):
            analytical_atr_band(2,3)

    def test_different_stop_geometry_widens_preentry_eligibility_not_rr_waiver(self):
        prior_atr=2.5
        base=entry_plan(100,prior_atr,**POLICIES["BASE_STOP125_TP300"])
        medium=entry_plan(100,prior_atr,**POLICIES["MODERATE_STOP100_TP250"])
        tight=entry_plan(100,prior_atr,**POLICIES["TIGHT_STOP075_TP225"])
        self.assertFalse(base["allowed"])
        self.assertEqual(base["reason"],"STOP_TOO_WIDE")
        for plan in (medium,tight):
            self.assertTrue(plan["allowed"])
            self.assertGreaterEqual(plan["planned_net_rr"],MIN_NET_RR)
            self.assertLessEqual(plan["gross_stop_fraction"],.03)
            self.assertLessEqual(plan["gross_target_fraction"],.08)
        # Only change risk geometry, never relax the user-required 2.0 floor.
        for policy in POLICIES.values():
            undersized=entry_plan(100,.4,**policy)
            self.assertFalse(undersized["allowed"])
        with self.assertRaisesRegex(ValueError,"INVALID_ATR_MULTIPLIER"):
            entry_plan(100,2.,stop_atr_mult=0)

    def test_rejection_causes_and_market_state_sum_to_original_signal(self):
        dates=list(pd.bdate_range("2026-01-05",periods=6))
        paths={("COIN",date):candle() for date in dates}
        flags=[True]*6
        meta=[{"atr":2.5,"regime":"BULL"} for _ in range(3)]+[
            {"atr":1., "regime":"BEAR"} for _ in range(2)]+[
            {"atr":None,"regime":"TRANSITION"}]
        base=preentry_counters(dates,flags,meta,paths,"COIN",
                               POLICIES["BASE_STOP125_TP300"])
        med=preentry_counters(dates,flags,meta,paths,"COIN",
                              POLICIES["MODERATE_STOP100_TP250"])
        self.assertEqual(base["original_signal_count"],6)
        self.assertEqual(base["passed_pre_entry_geometry"],0)
        self.assertEqual(base["rejection_causes"]["STOP_TOO_WIDE"],3)
        self.assertEqual(base["rejection_causes"]["NET_RR_BELOW_MINIMUM"],2)
        self.assertEqual(base["rejection_causes"]["MISSING_ATR_OR_ENTRY_BAR"],1)
        self.assertEqual(med["passed_pre_entry_geometry"],3)
        self.assertEqual(med["by_market_regime_at_signal"]["BULL"]["pass"],3)
        self.assertEqual(sum(v["signal"] for v in med["by_market_regime_at_signal"].values()),6)
        self.assertEqual(sum(med["rejection_causes"].values()),6)

    def test_simulated_accepted_trades_never_less_than_two_rr(self):
        dates=list(pd.bdate_range("2026-01-05",periods=9))
        paths={("COIN",date):candle() for date in dates}
        meta=[{"atr":2.5,"regime":"BULL"} for _ in dates]
        flags=[True,True,True,False,False,False,False,False,False]
        base=simulate(dates,flags,meta,paths,"COIN",1,"MIN_NET_RR_GATE",
                      plan_multipliers=POLICIES["BASE_STOP125_TP300"])
        moderate=simulate(dates,flags,meta,paths,"COIN",1,"MIN_NET_RR_GATE",
                          plan_multipliers=POLICIES["MODERATE_STOP100_TP250"])
        self.assertEqual(base["trades"],0)
        self.assertEqual(base["gate_counts"]["failed_rr"],3)
        self.assertEqual(base["gate_counts"]["rejected_by_reason"]["STOP_TOO_WIDE"],3)
        self.assertEqual(moderate["trades"],3)
        self.assertGreaterEqual(moderate["mean_planned_net_rr"],2.)
        self.assertEqual(moderate["exit_reason_counts"]["TIME_CLOSE"],3)


if __name__=="__main__":
    unittest.main()
