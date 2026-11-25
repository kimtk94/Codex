import unittest
import pandas as pd
from completed_session_policy import fetch_plan, inspect_us_prefix, US_KEYS, OTHER_KEYS


class CompletedSessionPolicyTests(unittest.TestCase):
    def test_incident_preclose(self):
        plan = fetch_plan("2026-11-25T11:15:46Z")
        self.assertEqual(plan["completed_xnys_session"], "2026-11-24")
        self.assertEqual(plan["exclusive_end_by_key"]["yf_vix"], "2026-11-25")
        self.assertEqual(len(US_KEYS), 14)
        self.assertEqual(len(OTHER_KEYS), 5)
        self.assertTrue(all(plan["exclusive_end_by_key"][k] is None for k in OTHER_KEYS))
        self.assertFalse(plan["source_finality_certified"])

    def test_regular_close_grace(self):
        self.assertEqual(fetch_plan("2026-11-25T21:29:59Z")["completed_xnys_session"], "2026-11-24")
        self.assertEqual(fetch_plan("2026-11-25T21:30:00Z")["completed_xnys_session"], "2026-11-25")

    def test_holiday_and_early_close(self):
        self.assertEqual(fetch_plan("2026-11-26T23:00:00Z")["completed_xnys_session"], "2026-11-25")
        self.assertEqual(fetch_plan("2026-11-27T18:29:59Z")["completed_xnys_session"], "2026-11-25")
        self.assertEqual(fetch_plan("2026-11-27T18:30:00Z")["completed_xnys_session"], "2026-11-27")

    def test_naive_clock_rejected(self):
        with self.assertRaisesRegex(ValueError, "AWARE_CLOCK"):
            fetch_plan("2026-11-25 12:00")

    def frame(self):
        return pd.DataFrame({"timestamp": pd.to_datetime(["2026-11-23", "2026-11-24", "2026-11-25"]),
                             "open": [20., 21., 22.], "high": [22., 23., 24.],
                             "low": [19., 20., 21.], "close": [21., 22., 23.]})

    def test_post_cutoff_not_modified(self):
        frame = self.frame()
        before = frame.copy(deep=True)
        d = inspect_us_prefix(frame, "yf_vix", "2026-11-24")
        self.assertEqual(d["status"], "POST_CUTOFF_ROWS_OBSERVED_HOLD")
        self.assertEqual(d["post_cutoff_dates"], ["2026-11-25"])
        self.assertEqual(d["prefix_rows"], 2)
        self.assertFalse(d["features_recomputed"])
        pd.testing.assert_frame_equal(frame, before)

    def test_null_tail_counted(self):
        frame = self.frame()
        frame.loc[2, "close"] = float("nan")
        self.assertEqual(inspect_us_prefix(frame, "yf_vix", "2026-11-24")["post_cutoff_rows"], 1)

    def test_missing_or_invalid_cutoff_holds(self):
        frame = self.frame()
        for sample in (frame.drop(index=1), frame.assign(high=[22., 20., 24.])):
            d = inspect_us_prefix(sample, "yf_vix", "2026-11-24")
            self.assertEqual(d["status"], "CUTOFF_ROW_MISSING_OR_INVALID_HOLD")

    def test_invalid_sequence_and_non_us_rejected(self):
        frame = self.frame()
        with self.assertRaises(ValueError):
            inspect_us_prefix(frame, "yf_usdkrw", "2026-11-24")
        with self.assertRaises(ValueError):
            inspect_us_prefix(pd.concat([frame, frame.iloc[[2]]]), "yf_vix", "2026-11-24")
        with self.assertRaises(ValueError):
            inspect_us_prefix(frame.iloc[::-1], "yf_vix", "2026-11-24")

    def test_no_tail_still_hold(self):
        d = inspect_us_prefix(self.frame().iloc[:2], "yf_vix", "2026-11-24")
        self.assertEqual(d["status"], "CUTOFF_ROW_PRESENT_RESEARCH_HOLD")
        self.assertFalse(d["approved_live"])
        self.assertFalse(d["ready_for_pit_training"])


if __name__ == "__main__":
    unittest.main()
