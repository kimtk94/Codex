import unittest
import numpy as np
import pandas as pd
import exchange_calendars as xc
from feature_basis_sensitivity import compare_asset,compare_context,context_series,paired_window


def sample():
    dates=pd.DatetimeIndex(xc.get_calendar("XNYS").sessions_in_range("2025-01-02","2026-10-30"))
    x=np.arange(len(dates))
    close=100+x*.03+np.sin(x/9)*2
    return pd.DataFrame({"timestamp":dates,"is_adjusted":False,"open":close,
                         "high":close+1,"low":close-1,"close":close})


class FeatureBasisTests(unittest.TestCase):
    def test_identity(self):
        a=sample()
        r,_=compare_asset(a,a.copy(),"yf_hyg","2026-10-30")
        self.assertEqual(r["metrics"]["RSI14"]["finite_pairs"],46)
        self.assertTrue(all(x["changed_pairs"]==0 for x in r["metrics"].values()))

    def test_constant_scaling_normalized_vs_absolute(self):
        a=sample()
        b=a.copy()
        b.loc[:,["open","high","low","close"]]*=.9
        b["is_adjusted"]=True
        r,_=compare_asset(a,b,"yf_hyg","2026-10-30")
        self.assertEqual(r["metrics"]["RSI14"]["changed_pairs"],0)
        self.assertEqual(r["metrics"]["NATR14"]["changed_pairs"],0)
        self.assertEqual(r["metrics"]["MACD_HIST_OVER_CLOSE"]["changed_pairs"],0)
        self.assertEqual(r["metrics"]["ATR14"]["changed_pairs"],46)

    def test_missing_session_never_bridged(self):
        a=sample()
        b=a.drop(a.index[-10])
        x,y,n=paired_window(a,b,"yf_hyg","2026-10-30")
        self.assertEqual(len(x),9)
        self.assertEqual(n,1)
        self.assertEqual(compare_asset(a,b,"yf_hyg","2026-10-30")[0]["status"],
                         "INSUFFICIENT_CONTIGUOUS_HISTORY_HOLD")

    def test_context_lag_and_no_future(self):
        a=sample()
        keys=("yf_hyg","yf_lqd","yf_tlt","yf_spy")
        pairs={k:paired_window(a,a.copy(),k,"2026-10-30")[:2] for k in keys}
        r=compare_context(pairs)
        self.assertTrue(all(x["changed_pairs"]==0 for x in r["metrics"].values()))
        frames={k:pairs[k][0].copy() for k in keys}
        baseline=context_series(frames)
        frames["yf_hyg"].iloc[-1,frames["yf_hyg"].columns.get_loc("close")]*=2
        pd.testing.assert_frame_equal(context_series(frames),baseline)

    def test_cutoff_excludes_later_revision_rows(self):
        a=sample()
        b=a.copy()
        b.loc[b.index[-1],"close"]=np.nan
        cutoff=str(pd.Timestamp(a.timestamp.iloc[-2]).date())
        r,_=compare_asset(a,b,"yf_hyg",cutoff)
        self.assertEqual(r["invalid_or_absent_pairs"],0)
        self.assertEqual(r["metrics"]["RSI14"]["changed_pairs"],0)
