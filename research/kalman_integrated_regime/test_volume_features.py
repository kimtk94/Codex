"""Leakage and strict-session tests for historical QLD/QQQ volume data."""
import unittest
import exchange_calendars as xcals
import pandas as pd
from research.kalman_integrated_regime.volume_features import volume_features


def fake_bars(sessions=23):
    cal=xcals.get_calendar("XNYS")
    days=cal.sessions_in_range("2026-08-03","2026-09-10")[:sessions]
    rows=[]
    for index,d in enumerate(days):
        start=cal.session_open(d)
        end=cal.session_close(d)
        stamps=pd.date_range(start,end-pd.Timedelta(minutes=15),freq="15min")
        for sym in ("QLD","QQQ"):
            for ts in stamps:
                rows.append({"market":sym,"candle_time_utc":ts.isoformat(),
                             "volume":200 if index==20 and sym=="QLD" else 100,
                             "unit_min":15})
    return pd.DataFrame(rows),pd.DatetimeIndex(days).tz_localize(None)


class TestVolumeFeatures(unittest.TestCase):
    def test_current_rvol_uses_only_previous_20_sessions(self):
        bars,days=fake_bars(23)
        f,qa=volume_features(bars,20)
        self.assertEqual(len(f),23)
        self.assertTrue(pd.isna(f.loc[days[19],"qld_rvol20"]))
        self.assertAlmostEqual(f.loc[days[20],"qld_rvol20"],2.)
        self.assertAlmostEqual(f.loc[days[20],"qqq_rvol20"],1.)
        self.assertAlmostEqual(f.loc[days[21],"qld_rvol20"],1.)
        self.assertEqual(qa["partial_or_missing_rth_rows"],0)

    def test_future_volume_cannot_change_prior_signal(self):
        bars,days=fake_bars(23)
        f,_=volume_features(bars)
        modified=bars.copy()
        later=(pd.to_datetime(modified.candle_time_utc,utc=True)
               .dt.tz_convert("America/New_York").dt.date==days[22].date())
        modified.loc[later,"volume"]=1_000_000
        f2,_=volume_features(modified)
        pd.testing.assert_series_equal(f.loc[days[20]],f2.loc[days[20]])

    def test_partial_session_is_missing_not_zero_and_blocks_history(self):
        bars,days=fake_bars(23)
        idx=bars.index[bars.market.eq("QLD") &
                       bars.candle_time_utc.str.startswith(str(days[7].date()))][0]
        f,qa=volume_features(bars.drop(idx))
        self.assertEqual(qa["partial_or_missing_rth_rows"],1)
        self.assertTrue(pd.isna(f.loc[days[7],"qld_rth_volume"]))
        self.assertTrue(pd.isna(f.loc[days[20],"qld_rvol20"]))
        self.assertAlmostEqual(f.loc[days[20],"qqq_rvol20"],1.)

    def test_duplicate_bar_hard_error(self):
        bars,_=fake_bars(6)
        bars=pd.concat([bars,bars.iloc[[0]]],ignore_index=True)
        with self.assertRaisesRegex(ValueError,"VOLUME_DUPLICATE_BAR"):
            volume_features(bars,5)


if __name__=="__main__":
    unittest.main()
