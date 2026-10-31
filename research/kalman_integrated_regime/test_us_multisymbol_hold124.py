"""Historical 1/2/4-session long-flat overnight accounting contracts."""
import unittest
import numpy as np
import pandas as pd
from research.kalman_integrated_regime.us_multisymbol_hold124 import (
    daily_ledger, one_session_path, HORIZONS, EXIT_POLICIES,
)


def make_path(price_open, lo=None, hi=None, close=None):
    c=price_open if close is None else close
    l=min(price_open,c) if lo is None else lo
    h=max(price_open,c) if hi is None else hi
    return pd.DataFrame([{"open":price_open,"high":h,"low":l,"close":c}])


def dummy_dates(n=9):
    days=list(pd.bdate_range("2026-04-06",periods=n))
    data={("COIN",d):make_path(100.) for d in days}
    return days,data


class MultiDayContracts(unittest.TestCase):
    def test_exact_four_session_hold_and_no_overlap(self):
        days,paths=dummy_dates()
        flags=[True,True,True,True,False,True,False,False,False]
        o=daily_ledger(days,flags,paths,"COIN",4,"RTH_FINAL_CLOSE")
        self.assertEqual(o["trades"],2)
        self.assertEqual(o["blocked_signals_while_holding"],3)
        self.assertEqual(o["trades_held_2plus_sessions"],2)
        self.assertEqual(o["untradable_end_window_signals"],0)
        self.assertEqual(o["exit_reasons"]["TIME_CLOSE"],2)
        self.assertAlmostEqual(o["cumulative_return_pct"],100*((1-.003)**2-1),places=5)

    def test_one_day_contract_matches_30bp_roundtrip_legacy(self):
        days,paths=dummy_dates()
        paths[("COIN",days[0])]=make_path(100,lo=99,hi=102,close=102)
        flag=[True,False,False,False,False,False,False,False,False]
        for policy in EXIT_POLICIES:
            o=daily_ledger(days,flag,paths,"COIN",1,policy)
            self.assertEqual(o["trades"],1)
            self.assertAlmostEqual(o["cumulative_return_pct"],1.7,places=5)
            self.assertEqual(o["trades_held_2plus_sessions"],0)

    def test_stop_first_and_overnight_gap_worse_than_stop(self):
        days,paths=dummy_dates()
        paths[("COIN",days[1])]=make_path(95,lo=93,hi=96,close=95.5)
        trade=[True]+[False]*8
        stop=daily_ledger(days,trade,paths,"COIN",4,"BARRIER_TP3_SL3")
        self.assertEqual(stop["trades"],1)
        self.assertEqual(stop["exit_reasons"]["STOP_GAP"],1)
        self.assertAlmostEqual(stop["cumulative_return_pct"],-5.3,places=5)
        path=make_path(100,lo=96,hi=104,close=100)
        self.assertEqual(one_session_path(path,100), (97.,"STOP_FIRST_AMBIGUOUS"))

    def test_overnight_mark_drawdown_and_realized_return_reconcile(self):
        days,paths=dummy_dates()
        paths[("COIN",days[0])]=make_path(100,lo=99,hi=101,close=101)
        paths[("COIN",days[1])]=make_path(98,lo=96,hi=99,close=97)
        flags=[True]+[False]*8
        result=daily_ledger(days,flags,paths,"COIN",2,"RTH_FINAL_CLOSE")
        # First day EOD +1% minus 15bps entry assumed; exit after
        # overnight price decline, net full position -3% minus 30bps.
        self.assertAlmostEqual(result["cumulative_return_pct"],-3.3,places=5)
        self.assertLess(result["mdd_marked_eod_pct"],-3)
        self.assertEqual(result["trades"],1)
        self.assertEqual(result["trades_held_2plus_sessions"],1)

    def test_tail_signals_explicitly_skipped_and_empty_policy_rejected(self):
        days,paths=dummy_dates()
        flags=[False]*6+[True]*3
        result=daily_ledger(days,flags,paths,"COIN",4,"RTH_FINAL_CLOSE")
        self.assertEqual(result["trades"],0)
        self.assertEqual(result["untradable_end_window_signals"],3)
        self.assertEqual(result["cumulative_return_pct"],0.)
        with self.assertRaisesRegex(ValueError,"INVALID_POLICY_OR_HORIZON"):
            daily_ledger(days,flags,paths,"COIN",5,"RTH_FINAL_CLOSE")
        with self.assertRaisesRegex(ValueError,"MISSING_SESSION_PATH"):
            daily_ledger(days,flags,{},"COIN",4,"RTH_FINAL_CLOSE")


if __name__=="__main__":
    unittest.main()
