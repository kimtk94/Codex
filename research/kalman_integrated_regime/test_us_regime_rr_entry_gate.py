"""Contracts: R:R is an actual entry veto, prior-close regime, fees, no overlaps."""
import unittest
import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_regime_rr_entry_gate import (
    entry_plan, exit_for_session, simulate, VARIANTS, MIN_NET_RR,
    trailing_atr_by_signal_close,
)


def two_bars(entry=100,second_close=100.5):
    return pd.DataFrame([
        {"open":99.5,"high":100.0,"low":99.4,"close":99.9},
        {"open":entry,"high":max(entry,second_close),"low":min(entry,second_close),
         "close":second_close},
    ])


class EntryRRGateContracts(unittest.TestCase):
    def test_rr_rejects_low_reward_and_accepts_only_good_plan(self):
        acceptable=entry_plan(100.,1.)
        self.assertTrue(acceptable["allowed"])
        self.assertGreaterEqual(acceptable["planned_net_rr"],MIN_NET_RR)
        self.assertAlmostEqual(acceptable["net_winner_fraction"],.027)
        self.assertAlmostEqual(acceptable["net_planned_stop_fraction"],.0155)
        low=entry_plan(100.,.2)
        self.assertFalse(low["allowed"])
        self.assertEqual(low["reason"],"NET_RR_BELOW_MINIMUM")
        high=entry_plan(100.,3.)
        self.assertFalse(high["allowed"])
        self.assertEqual(high["reason"],"STOP_TOO_WIDE")

    def test_exact_stop_on_ambiguous_bar_and_gap_through_stop(self):
        p=pd.DataFrame([{"open":100.,"low":98.,"high":105.,"close":100.},
                        {"open":100.,"low":99.,"high":100.5,"close":100.}])
        self.assertEqual(exit_for_session(p,0,98.75,103.),
                         (98.75,"BOTH_HIT_STOP_FIRST"))
        p2=pd.DataFrame([{"open":97.,"low":96.,"high":97.5,"close":97.}])
        self.assertEqual(exit_for_session(p2,0,98.75,103.),
                         (97.,"STOP_GAP"))
        self.assertEqual(exit_for_session(p,1,98.75,103.),(None,None))

    def test_actual_entry_gate_declines_risk_and_bear(self):
        dates=list(pd.bdate_range("2026-02-02",periods=8))
        paths={("COIN",d):two_bars() for d in dates}
        signals=[True,True,True,False,False,False,False,False]
        # day 1 good bull 1% ATR, day 2 bear also good, day 3 low ratio.
        meta=[{"atr":1.,"regime":"BULL"},{"atr":1.,"regime":"BEAR"},
              {"atr":.2,"regime":"BULL"}]+[
                  {"atr":1.,"regime":"BULL"} for _ in range(5)]
        base=simulate(dates,signals,meta,paths,"COIN",1,VARIANTS[0])
        rr=simulate(dates,signals,meta,paths,"COIN",1,VARIANTS[1])
        bull=simulate(dates,signals,meta,paths,"COIN",1,VARIANTS[2])
        self.assertEqual(base["trades"],3)
        self.assertEqual(rr["trades"],2)
        self.assertEqual(rr["gate_counts"]["failed_rr"],1)
        self.assertEqual(bull["trades"],1)
        self.assertEqual(bull["gate_counts"]["blocked_regime"],1)
        self.assertGreater(bull["mean_planned_net_rr"],1.5)
        self.assertIsNotNone(bull["realized_expectancy_R"])
        self.assertEqual(bull["by_market_regime"]["BEAR"]["trades"],0)

    def test_overlapping_signals_are_ignored_until_position_closes(self):
        dates=list(pd.bdate_range("2026-02-02",periods=10))
        paths={("COIN",d):two_bars() for d in dates}
        meta=[{"atr":1.,"regime":"BULL"} for _ in dates]
        flags=[True]*len(dates)
        result=simulate(dates,flags,meta,paths,"COIN",4,VARIANTS[2])
        self.assertEqual(result["trades"],2)
        self.assertGreaterEqual(result["gate_counts"]["blocked_overlap"],6)
        self.assertTrue(result["mean_planned_net_rr"]>=MIN_NET_RR)

    def test_atr_fitted_through_completed_trading_session_only(self):
        dates=pd.bdate_range("2025-03-03",periods=21)
        paths={("COIN",d):two_bars() for d in dates}
        p1=trailing_atr_by_signal_close(paths)
        self.assertIsNone(p1.get(("COIN",dates[0])))
        self.assertIn(("COIN",dates[13]),p1)
        modified=dict(paths)
        modified[("COIN",dates[-1])]=two_bars(110,115)
        p2=trailing_atr_by_signal_close(modified)
        for d in dates[:-1]:
            self.assertEqual(p1.get(("COIN",d)),p2.get(("COIN",d)))


if __name__=="__main__":
    unittest.main()
