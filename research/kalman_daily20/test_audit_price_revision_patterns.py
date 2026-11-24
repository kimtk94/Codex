"""Tests distinguish session-close revision, history scaling and mixed drift."""
from __future__ import annotations
import unittest

import numpy as np
import pandas as pd

from audit_price_revision_patterns import summarize_pair


class PriceRevisionPatternTests(unittest.TestCase):
    def frame(self):
        days=pd.bdate_range("2024-01-01",periods=400)
        days=pd.DatetimeIndex([*days[:-1],pd.Timestamp("2026-11-20")])
        close=pd.Series(np.linspace(90,110,len(days)),index=days)
        return pd.DataFrame({
            "open":close*.998,"high":close*1.01,"low":close*.99,
            "close":close,"volume":10_000
        },index=days)

    def pair(self,a,b):
        return summarize_pair(a,b,symbol="SPY",left="one",right="two")

    def test_no_numeric_change(self):
        a=self.frame()
        r=self.pair(a,a.copy())
        self.assertEqual(r["classify_revision"],"NUMERIC_OHLCV_STABLE")
        self.assertEqual(r["nonterminal_close_changed"],0)

    def test_only_last_close_changed(self):
        a=self.frame();b=a.copy()
        b.loc[b.index[-1],"close"]*=.98
        r=self.pair(a,b)
        self.assertEqual(r["classify_revision"],"TERMINAL_CLOSE_REVISION_ONLY")
        self.assertTrue(r["terminal_material_gt10bps"])
        self.assertEqual(r["nonterminal_close_material_gt10bps"],0)

    def test_global_price_scaling_without_volume_changes(self):
        a=self.frame();b=a.copy()
        for c in ("open","high","low","close"):
            b[c]=a[c]*.99
        r=self.pair(a,b)
        self.assertTrue(r["global_scale_candidate"])
        self.assertEqual(r["classify_revision"],"GLOBAL_HISTORICAL_PRICE_SCALING_CANDIDATE")
        self.assertFalse(r["volume_changed"])

    def test_local_historical_revision_with_terminal_change(self):
        a=self.frame();b=a.copy()
        b.loc[b.index[-100]:,"close"]*=1.007
        r=self.pair(a,b)
        self.assertEqual(r["classify_revision"],"TERMINAL_AND_MATERIAL_HISTORICAL_REVISIONS")
        self.assertGreater(r["nonterminal_close_material_gt10bps"],0)

    def test_sub_1bp_historical_numeric_drift_without_terminal_revision(self):
        a=self.frame();b=a.copy()
        b.loc[b.index[-100:-1],"close"]*=1.0000005
        r=self.pair(a,b)
        self.assertEqual(r["classify_revision"],"SUB_1BP_HISTORY_DRIFT_ONLY")
        self.assertEqual(r["nonterminal_close_material_gt1bp"],0)
        self.assertGreater(r["nonterminal_close_changed"],0)
        self.assertFalse(r["terminal_changed"])

    def test_terminal_with_sub_1bp_history_drift(self):
        a=self.frame();b=a.copy()
        b.loc[b.index[-100:-1],"close"]*=1.0000005
        b.loc[b.index[-1],"close"]*=.98
        r=self.pair(a,b)
        self.assertEqual(r["classify_revision"],"TERMINAL_WITH_SUB_1BP_HISTORY_DRIFT")
        self.assertEqual(r["nonterminal_close_material_gt1bp"],0)
        self.assertTrue(r["terminal_changed"])

    def test_volume_only_change(self):
        a=self.frame();b=a.copy()
        b.loc[b.index[-1],"volume"]=99999
        r=self.pair(a,b)
        self.assertEqual(r["classify_revision"],"OTHER_OHLCV_OR_VOLUME_REVISION")
        self.assertEqual(r["nonterminal_close_changed"],0)
        self.assertTrue(r["volume_changed"])

    def test_asof_must_be_present(self):
        a=self.frame().iloc[:-1]
        with self.assertRaisesRegex(RuntimeError,"NO_COMPLETE_COMMON_SESSIONS"):
            self.pair(a,a)


if __name__ == "__main__":
    unittest.main()
