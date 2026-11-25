import unittest
import pandas as pd
from completed_session_policy import (fetch_plan, inspect_us_prefix, US_KEYS, OTHER_KEYS,
                                      split_selected_universe, reconcile_staged_us)


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

    def test_split_actual_selected_config_is_lossless(self):
        from pathlib import Path
        import tempfile
        import copy
        from refresh_ci import select_universe
        cfg_path = Path(__file__).resolve().parents[2] / "kalman-toss-gateway/config/market-data-v2-universe.json"
        with tempfile.TemporaryDirectory() as tmp:
            cfg = select_universe(cfg_path, Path(tmp) / "selected.json")
        before = copy.deepcopy(cfg)
        plan = split_selected_universe(cfg, "2026-11-25T11:15:46Z")
        self.assertEqual(cfg, before)
        groups = plan["groups"]
        self.assertEqual(len(groups["US_COMPLETED"]["config"]["assets"]), 14)
        self.assertEqual(len(groups["NON_US_EXISTING"]["config"]["assets"]), 5)
        self.assertEqual(groups["US_COMPLETED"]["exclusive_end"], "2026-11-25")
        self.assertIsNone(groups["NON_US_EXISTING"]["exclusive_end"])
        actual = {a["key"]: a for group in groups.values() for a in group["config"]["assets"]}
        self.assertEqual(actual, {a["key"]: a for a in before["assets"]})
        self.assertFalse(plan["executed"])
        cfg["assets"].pop()
        with self.assertRaises(ValueError):
            split_selected_universe(cfg, "2026-11-25T11:15:46Z")

    def canonical(self):
        f = self.frame()
        f["market"], f["symbol"], f["currency"], f["source"] = "US", "VIX", "USD", "yfinance"
        f["adj_close"], f["volume"] = f.close, 0.
        f["source_asof"], f["retrieved_at"], f["is_adjusted"] = f.timestamp, "initial", False
        return f

    @staticmethod
    def feature_builder(f):
        # Deterministic synthetic feature; not a claim of TA-Lib execution.
        return f[["timestamp", "symbol"]].assign(
            rolling_close=f.close.rolling(2).mean())

    def reconcile(self, observed, bounded, features):
        return reconcile_staged_us(observed, bounded, features, key="yf_vix",
                                   cutoff="2026-11-24", feature_builder=self.feature_builder)

    def test_bounded_prefix_and_features_reconciled_but_hold(self):
        f = self.canonical()
        bounded = f.iloc[:2].copy()
        bounded["retrieved_at"] = "later"
        features = self.feature_builder(bounded)
        before = (f.copy(deep=True), bounded.copy(deep=True), features.copy(deep=True))
        d = self.reconcile(f, bounded, features)
        self.assertEqual(d["status"], "STAGED_PREFIX_AND_FEATURES_RECONCILED_RESEARCH_HOLD")
        self.assertTrue(d["feature_reproduction_verified"])
        self.assertFalse(d["ready_for_pit_training"])
        for a, b in zip((f, bounded, features), before):
            pd.testing.assert_frame_equal(a, b)

    def test_revision_or_basis_change_cannot_pass(self):
        f = self.canonical()
        for field, value in (("close", 20.5), ("is_adjusted", True), ("source_asof", pd.Timestamp("2026-11-22"))):
            bounded = f.iloc[:2].copy()
            bounded.loc[0, field] = value
            d = self.reconcile(f, bounded, self.feature_builder(bounded))
            self.assertIn("ELIGIBLE_PREFIX_CHANGED", d["reasons"])
            self.assertFalse(d["prefix_identity_verified"])

    def test_staged_tail_and_missing_cutoff_hold(self):
        f = self.canonical()
        d = self.reconcile(f, f.copy(), self.feature_builder(f))
        self.assertIn("STAGED_POST_CUTOFF_ROWS", d["reasons"])
        d = self.reconcile(f, f.iloc[:1], self.feature_builder(f.iloc[:1]))
        self.assertIn("CUTOFF_ROW_MISSING_OR_INVALID", d["reasons"])

    def test_wrong_feature_row_or_value_hold(self):
        f = self.canonical()
        bounded = f.iloc[:2].copy()
        features = self.feature_builder(bounded)
        bad = features.iloc[:1]
        self.assertIn("RAW_FEATURE_ROW_IDENTITY_MISMATCH", self.reconcile(f, bounded, bad)["reasons"])
        bad = features.copy()
        bad.loc[1, "rolling_close"] = 1.
        self.assertIn("FEATURE_VALUES_OR_SCHEMA_MISMATCH", self.reconcile(f, bounded, bad)["reasons"])

    def test_feature_rebuild_failure_is_hold(self):
        f = self.canonical()
        bounded = f.iloc[:2].copy()
        def fail(_):
            raise RuntimeError("fixture error")
        d = reconcile_staged_us(f, bounded, self.feature_builder(bounded), key="yf_vix",
                                cutoff="2026-11-24", feature_builder=fail)
        self.assertEqual(d["reasons"], ["FEATURE_REBUILD_UNAVAILABLE"])
        self.assertFalse(d["feature_reproduction_verified"])


if __name__ == "__main__":
    unittest.main()
