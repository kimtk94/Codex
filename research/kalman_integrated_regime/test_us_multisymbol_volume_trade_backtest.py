"""Research-only execution contract tests for fixed one-session 5-symbol trading."""
import unittest

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_multisymbol_volume_trade_backtest import (
    EXIT_POLICIES, intraday_exit, trade_ledger, annual, TP, SL
)
from research.kalman_integrated_regime.us_multisymbol_volume_screen import matched_cohorts
from research.kalman_integrated_regime.test_us_multisymbol_volume_screen import synthetic_daily


def path(op=100., bar_high=100.2, bar_low=99.8, close=100.1):
    return pd.DataFrame([
        {"open":op, "high":max(op,bar_high),"low":min(op,bar_low),"close":close}
    ])


class ExecutionContracts(unittest.TestCase):
    def test_barrier_stop_first_when_both_hit(self):
        x=path(bar_high=104,bar_low=96,close=101)
        self.assertEqual(intraday_exit(x,"SAME_SESSION_TP3_SL3"),(-SL,"AMBIGUOUS_STOP_FIRST"))
        self.assertAlmostEqual(intraday_exit(x,"NEXT_RTH_CLOSE")[0],.01)

    def test_barrier_gap_loss_not_synthetic_stop_fill(self):
        x=pd.DataFrame([
            {"open":100.,"high":100.5,"low":99.5,"close":100.},
            {"open":95.,"high":95.2,"low":94.,"close":94.8},
        ])
        result,reason=intraday_exit(x,"SAME_SESSION_TP3_SL3")
        self.assertAlmostEqual(result,-.05)
        self.assertEqual(reason,"STOP_GAP")

    def test_fee_slippage_accounting_and_cash_days(self):
        days=pd.to_datetime(["2026-03-03","2026-03-04","2026-03-05"])
        paths={("SPY",day):path(close=102.) for day in days}
        flags=np.array([True,False,True])
        a=trade_ledger(days,flags,paths,"SPY",policy="NEXT_RTH_CLOSE")
        b=trade_ledger(days,flags,paths,"SPY",policy="NEXT_RTH_CLOSE",fee=0,slip=0)
        self.assertEqual(a["trades"],2)
        self.assertEqual(a["signal_days"],3)
        self.assertEqual(a["win_rate_executed"],1.)
        self.assertAlmostEqual(a["cumulative_return_pct"],100*((1.017**2)-1),places=5)
        self.assertGreater(b["cumulative_return_pct"],a["cumulative_return_pct"])
        self.assertAlmostEqual(a["aggregate_friction_unit_return"],.006)
        self.assertEqual(a["exit_reason_counts"]["EOD"],2)

    def test_no_signal_is_flat_and_equity_unaffected(self):
        days=pd.to_datetime(["2026-03-03","2026-03-04"])
        paths={("SPY",day):path(close=90.) for day in days}
        ret=trade_ledger(days,[False,False],paths,"SPY",policy="NEXT_RTH_CLOSE")
        self.assertEqual(ret["cumulative_return_pct"],0)
        self.assertEqual(ret["max_drawdown_eod_pct"],0)
        self.assertIsNone(ret["win_rate_executed"])
        with self.assertRaisesRegex(ValueError,"MISSING_COMPLETE_BAR_PATH"):
            trade_ledger(days,[True,False],{},"SPY",policy="NEXT_RTH_CLOSE")

    def test_equal_dates_fee_and_purged_training_across_all_arms(self):
        d=synthetic_daily()
        tr,te=matched_cohorts(d,2025)
        te=te.loc[te.date_ny.dt.month.le(10)&te.next_session_date.dt.month.le(10)]
        dates=list(te.next_session_date)
        paths={("SPY",day):path(close=100.5,bar_high=104,bar_low=99.5)
               for day in dates}
        r=annual("SPY",tr,te,paths,2025)
        self.assertEqual(r["test_n"],len(te))
        self.assertLess(r["last_available_train_outcome"],"2025-01-01")
        self.assertEqual(set(r["policies"]),set(EXIT_POLICIES))
        for policy,record in r["policies"].items():
            self.assertEqual(
                {value["signal_days"] for value in record["arms"].values()},
                {len(te)})
            self.assertEqual(record["arms"]["ALWAYS_INTRADAY_LONG"]["trades"],len(te))
            self.assertEqual(len(record["paired_contrasts"]),2)


if __name__=="__main__":
    unittest.main()
