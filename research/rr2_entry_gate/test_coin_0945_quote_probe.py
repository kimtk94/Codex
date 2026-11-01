"""Synthetic original-model COIN 09:45 SIP quote provenance and chronology checks."""
import unittest
from datetime import datetime, timezone, timedelta

from coin_0945_quote_probe import select_pre_quote, percentile, selected_B, audit
from test_coin_signal_replay import synthetic_sessions, row


def quote(t, bid=99.9,ask=100.1, sizes=None):
    return {"t":t.isoformat().replace("+00:00","Z"),"bp":bid,"ap":ask,
            "bx":"Q","ax":"Q","bs":2,"as":3}


class QuotePilotContracts(unittest.TestCase):
    def test_pre_entry_no_future_quote_even_if_future_is_better(self):
        t=datetime(2026,5,1,13,45,tzinfo=timezone.utc)
        q=[quote(t+timedelta(milliseconds=1),99,100),
           quote(t-timedelta(milliseconds=200),99.95,100.05)]
        out=select_pre_quote(q,t)
        self.assertEqual(out["status"],"QUOTE_PROXY_ELIGIBLE")
        self.assertAlmostEqual(out["ap"],100.05)
        self.assertAlmostEqual(out["quote_age_ms"],200)
        self.assertEqual(select_pre_quote(q[:1],t)["status"],"NO_PRE_ENTRY_QUOTE")
        # Even an equal-timestamp exchange quote is not proven available at
        # the instant the 09:45 marketable order would be sent.
        self.assertEqual(select_pre_quote([quote(t)],t)["status"],"NO_PRE_ENTRY_QUOTE")
        self.assertEqual(select_pre_quote(
            [quote(t-timedelta(milliseconds=1400))],t,max_age_ms=1000)["status"],
            "STALE_PRE_ENTRY_QUOTE")
        self.assertEqual(select_pre_quote(
            [quote(t-timedelta(milliseconds=1400))],t,max_age_ms=2000)["status"],
            "QUOTE_PROXY_ELIGIBLE")

    def test_missing_stale_crossed_bad_quote_rejected(self):
        t=datetime(2026,5,1,13,45,tzinfo=timezone.utc)
        self.assertEqual(select_pre_quote([],t)["status"],"NO_PRE_ENTRY_QUOTE")
        self.assertEqual(select_pre_quote([quote(t-timedelta(seconds=4))],t)["status"],"STALE_PRE_ENTRY_QUOTE")
        self.assertEqual(select_pre_quote([quote(t-timedelta(milliseconds=10),100.1,100.0)],t)["status"],"CROSSED_ZERO_OR_INVALID_QUOTE")
        self.assertEqual(select_pre_quote([quote(t-timedelta(milliseconds=10),90,101)],t)["status"],"EXTREME_SPREAD_QUOTE")
        with self.assertRaisesRegex(ValueError,"NAIVE_ENTRY_TIMESTAMP"):
            select_pre_quote([quote(t)],t.replace(tzinfo=None))

    def test_zero_sample_not_interpreted_as_fill(self):
        self.assertIsNone(percentile([],.5))
        self.assertEqual(percentile([2.,3.,4.],.5),3)

    def test_24_cohort_required_before_api_calls(self):
        sessions,q=synthetic_sessions()
        ledger=[row(sessions,22,"a"),row(sessions,24,"b")]
        with self.assertRaisesRegex(ValueError,"COHORT_CARDINALITY_MISMATCH"):
            selected_B(sessions,ledger)
        with self.assertRaisesRegex(ValueError,"COHORT_CARDINALITY_MISMATCH"):
            audit(sessions,ledger,"test-key","test-secret",
                  fetcher=lambda *args: self.fail("called external data source"))


if __name__=="__main__":
    unittest.main()
