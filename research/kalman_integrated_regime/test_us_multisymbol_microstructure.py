"""Contract tests for reusable U.S. stock/ETF SIP microstructure research."""
import unittest

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_multisymbol_microstructure import (
    approved_us_symbols, select_symbols, symbol_volume_features
)


def synthetic_bars():
    cal=xcals.get_calendar("XNYS")
    days=cal.sessions_in_range("2026-08-03","2026-09-15")[:24]
    records=[]
    for i,day in enumerate(days):
        opening=cal.session_open(day)
        closing=cal.session_close(day)
        for symbol in ("SPY","MU","COIN"):
            for ts in pd.date_range(opening,closing-pd.Timedelta(minutes=15),freq="15min"):
                records.append({
                    "market":symbol,"candle_time_utc":ts.isoformat(),
                    "volume":200 if (symbol=="MU" and i==20) else 100,
                    "unit_min":15
                })
    return pd.DataFrame(records),days


class MultiSymbolContracts(unittest.TestCase):
    def test_allowlist_is_config_backed_no_crypto_or_indices(self):
        x=approved_us_symbols()
        for v in ("QLD","QQQ","SPY","IWM","SMH","MU","COIN"):
            self.assertIn(v,x)
        for v in ("BTC-USD","^GSPC","KRW=X","^KS11","BTC/USD"):
            self.assertNotIn(v,x)
        self.assertEqual(select_symbols("spy,mu,coin",x),("SPY","MU","COIN"))
        with self.assertRaisesRegex(ValueError,"SYMBOL_NOT_IN_APPROVED"):
            select_symbols("BTC-USD",x)
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            select_symbols("SPY,SPY",x)
        with self.assertRaisesRegex(ValueError,"BAD_SYMBOL_COUNT"):
            select_symbols("QQQ,SPY,IWM,SMH,MU,COIN",x)

    def test_rvol_is_symbol_specific_and_shifted(self):
        bars,dates=synthetic_bars()
        result,qa=symbol_volume_features(bars)
        self.assertEqual(qa["symbol_count"],3)
        self.assertEqual(qa["partial_or_missing_symbol_sessions"],0)
        def at(sym,idx):
            return result.loc[(result.symbol==sym)&
                              result.date_ny.eq(pd.Timestamp(dates[idx]).tz_localize(None))].iloc[0]
        self.assertTrue(np.isnan(at("MU",19).rvol20))
        self.assertAlmostEqual(at("MU",20).rvol20,2.)
        self.assertAlmostEqual(at("SPY",20).rvol20,1.)
        self.assertAlmostEqual(at("COIN",20).rvol20,1.)
        self.assertAlmostEqual(at("MU",21).rvol20,1.)
        self.assertTrue(pd.isna(at("SPY",20).volume_z20))

    def test_missing_bar_invalidates_only_one_symbol_and_rolling_history(self):
        bars,dates=synthetic_bars()
        # Remove one MU RTH bar on session 7, preserving other symbols.
        target=pd.Timestamp(dates[7]).strftime("%Y-%m-%d")
        removal=bars.index[
            bars.market.eq("MU") &
            bars.candle_time_utc.str.startswith(target)
        ][0]
        result,qa=symbol_volume_features(bars.drop(removal))
        self.assertEqual(qa["partial_or_missing_symbol_sessions"],1)
        day=pd.Timestamp(dates[20]).tz_localize(None)
        row=result.loc[result.date_ny.eq(day)].set_index("symbol")
        self.assertTrue(np.isnan(row.loc["MU","rvol20"]))
        self.assertAlmostEqual(row.loc["SPY","rvol20"],1.)
        self.assertAlmostEqual(row.loc["COIN","rvol20"],1.)

    def test_duplicate_rejected(self):
        bars,_=synthetic_bars()
        with self.assertRaisesRegex(ValueError,"DUPLICATED_SIP_BAR"):
            symbol_volume_features(pd.concat([bars,bars.iloc[:1]],ignore_index=True))


if __name__=="__main__":
    unittest.main()
