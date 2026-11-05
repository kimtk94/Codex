"""No-network regressions for SIP research bar acquisition and time integrity."""
import unittest
from unittest.mock import Mock
import pandas as pd
from research.kalman_integrated_regime.sip_backfill import (
    SYMBOLS, month_ranges, coverage, make_daily, request_page, ProviderError,
)


class SIPBackfillContracts(unittest.TestCase):
    def test_month_windows_are_exclusive_and_contiguous(self):
        ranges = list(month_ranges("2024-01-01", "2024-04-02"))
        self.assertEqual([(str(a.date()), str(b.date())) for a, b in ranges],
                         [("2024-01-01", "2024-02-01"),
                          ("2024-02-01", "2024-03-01"),
                          ("2024-03-01", "2024-04-01"),
                          ("2024-04-01", "2024-04-02")])

    def test_no_credentials_in_error(self):
        client = Mock()
        response = Mock(status_code=403, text="token_should_not_be_logged")
        client.get.return_value = response
        with self.assertRaisesRegex(ProviderError, "ALPACA_HTTP_403") as cm:
            request_page(client, "secret_key", "secret", {"feed": "sip"}, max_retries=1)
        self.assertNotIn("secret", str(cm.exception))
        self.assertNotIn("token_should", str(cm.exception))

    def test_early_close_and_full_calendar_contiguity(self):
        d = pd.Timestamp("2025-11-28")
        times = pd.date_range("2025-11-28 09:30", periods=14, freq="15min",
                              tz="America/New_York")
        records = []
        for s in SYMBOLS:
            for ts in times:
                records.append({"market": s, "candle_time_utc": ts.tz_convert("UTC").isoformat(),
                                "open": 100., "high": 101., "low": 99.,
                                "close": 100., "unit_min": 15})
        frame = pd.DataFrame(records)
        audit, complete, dates = coverage(frame, "2025-11-28", "2025-11-29")
        self.assertEqual(audit["QLD"]["complete_sessions"], 1)
        self.assertEqual(audit["QQQ"]["complete_sessions"], 1)
        daily = make_daily(complete, dates)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily.iloc[0]["close_qqq"], 100.)

    def test_partial_session_not_promoted_to_full_day(self):
        day1 = pd.date_range("2025-02-03 09:30", periods=26, freq="15min",
                              tz="America/New_York")
        day2 = pd.date_range("2025-02-04 09:30", periods=26, freq="15min",
                              tz="America/New_York")
        bars = []
        for sym in SYMBOLS:
            for ts in list(day1) + list(day2):
                if sym == "QLD" and ts == day2[10]:
                    continue
                bars.append({"market": sym, "candle_time_utc": ts.tz_convert("UTC").isoformat(),
                             "open": 100., "high": 101., "low": 99.,
                             "close": 100., "unit_min": 15})
        audit, complete, dates = coverage(pd.DataFrame(bars), "2025-02-03", "2025-02-05")
        self.assertEqual(audit["QLD"]["complete_sessions"], 1)
        self.assertEqual(audit["QLD"]["partial_by_year"]["2025"], 1)
        daily = make_daily(complete, dates)
        self.assertEqual(len(daily), 2)
        self.assertTrue(pd.isna(daily.iloc[1]["close_qld"]))
        self.assertFalse(pd.isna(daily.iloc[1]["close_qqq"]))


if __name__ == "__main__":
    unittest.main()
