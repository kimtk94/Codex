"""Contract tests for private US multisymbol historical 15m SIP backfill."""
import unittest

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.test_us_multisymbol_microstructure import synthetic_bars
from research.kalman_integrated_regime.us_multisymbol_bar_backfill import (
    summarize, get_months, DownloadError,
)


class MockResponse:
    status_code=200
    def __init__(self,data):
        self.data=data
    def json(self):
        return self.data


class MockSession:
    def __init__(self,output):
        self.output=output
        self.calls=[]
    def get(self,url,params,headers,timeout):
        self.calls.append(dict(params))
        return MockResponse(self.output)


class MultiSymbolBackfillContracts(unittest.TestCase):
    def test_complete_bars_and_tradecount_optional(self):
        bars,days=synthetic_bars()
        bars["trade_count"]=np.nan
        bars["vwap"]=np.nan
        bars["open"]=100.0
        bars["high"]=101.0
        bars["low"]=99.0
        bars["close"]=100.0
        report=summarize(
            bars,{"timeframe":"15Min","feed":"sip","adjustment":"all"},
            "2026-08-03","2026-09-15")
        self.assertEqual(report["data_qa"]["symbol_count"],3)
        self.assertEqual(report["data_qa"]["complete_symbol_sessions"],72)
        self.assertEqual(report["data_qa"]["partial_or_missing_symbol_sessions"],0)
        self.assertEqual(report["by_symbol"]["MU"]["bar_vwap_present"],0)
        self.assertTrue(report["hold_live"])

    def test_incomplete_session_has_hold_not_volume_zero(self):
        bars,days=synthetic_bars()
        bars["trade_count"]=1
        bars["vwap"]=100.
        # Select COIN explicitly; input rows begin with SPY and should not
        # accidentally invalidate a different symbol.
        coin_first=bars.index[bars.market.eq("COIN")][0]
        partial=bars.drop(coin_first)
        report=summarize(partial,{"adjustment":"all"},"2026-08-03","2026-09-15")
        self.assertEqual(report["data_qa"]["partial_or_missing_symbol_sessions"],1)
        self.assertEqual(report["by_symbol"]["COIN"]["years"]["2026"]["missing_or_partial_rth_sessions"],1)
        self.assertEqual(report["status"],"HOLD_PARTIAL_SESSIONS")

    def test_alpaca_multi_symbols_and_fields_page(self):
        stamp="2026-10-29T14:00:00Z"
        bar={"t":stamp,"o":100.,"h":101.,"l":99.,"c":100.,
             "v":200,"n":5,"vw":100.1}
        payload={"bars":{"SPY":[bar],"MU":[bar]},"next_page_token":None}
        sess=MockSession(payload)
        frame,qa=get_months(sess,("SPY","MU"),
                           pd.Timestamp("2026-10-01"),
                           pd.Timestamp("2026-11-01"),
                           "test-key","test-secret")
        self.assertEqual(qa["total_bars"],2)
        self.assertEqual(qa["request_pages"],1)
        self.assertEqual(set(frame.market.unique()),{"SPY","MU"})
        self.assertEqual(frame.loc[0,"trade_count"],5)
        self.assertEqual(frame.loc[0,"vwap"],100.1)
        self.assertEqual(sess.calls[0]["adjustment"],"all")
        self.assertEqual(sess.calls[0]["feed"],"sip")

    def test_duplicate_pages_hard_error(self):
        stamp="2026-10-29T14:00:00Z"
        bar={"t":stamp,"o":100.,"h":101.,"l":99.,"c":100.,"v":200}
        payload={"bars":{"SPY":[bar],"MU":[bar]},"next_page_token":"cursor_1"}
        sess=MockSession(payload)
        with self.assertRaisesRegex(DownloadError,"SIP_REPEAT_PAGINATION_CURSOR"):
            get_months(sess,("SPY","MU"),pd.Timestamp("2026-10-01"),
                       pd.Timestamp("2026-11-01"),"test-key","test-secret")


if __name__=="__main__":
    unittest.main()
