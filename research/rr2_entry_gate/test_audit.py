"""Offline deterministic contract tests for the RR2 research gate."""
import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("audit.py")
spec = importlib.util.spec_from_file_location("rr2_audit", MODULE)
rr2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr2)


class GateContracts(unittest.TestCase):
    def test_lower_thresholds(self):
        for name, minimum in (
            ("baseline_1p25_3p00", .018),
            ("A_1p00_2p50", .018),
            ("B_0p75_2p25", .012),
        ):
            self.assertTrue(rr2.assess(minimum, rr2.ARMS[name])["accepted"], name)
            self.assertIn("NET_RR_BELOW_2", rr2.assess(minimum - .0001, rr2.ARMS[name])["reasons"])

    def test_upper_caps_reject_not_clip(self):
        self.assertFalse(rr2.assess(.025, rr2.ARMS["baseline_1p25_3p00"])["accepted"])
        self.assertIn("STOP_CAP_EXCEEDED", rr2.assess(.025, rr2.ARMS["baseline_1p25_3p00"])["reasons"])
        self.assertTrue(rr2.assess(.025, rr2.ARMS["A_1p00_2p50"])["accepted"])
        self.assertTrue(rr2.assess(.025, rr2.ARMS["B_0p75_2p25"])["accepted"])
        self.assertTrue(rr2.assess(.0355, rr2.ARMS["B_0p75_2p25"])["accepted"])
        self.assertIn("TARGET_CAP_EXCEEDED", rr2.assess(.036, rr2.ARMS["B_0p75_2p25"])["reasons"])

    def test_multiple_causes_and_cost(self):
        x = rr2.assess(.050, rr2.ARMS["baseline_1p25_3p00"])
        self.assertEqual(set(x["reasons"]), {"STOP_CAP_EXCEEDED", "TARGET_CAP_EXCEEDED"})
        self.assertAlmostEqual(rr2.assess(.018, rr2.ARMS["baseline_1p25_3p00"])["net_rr"], 2.0)
        self.assertLess(rr2.assess(.0179, rr2.ARMS["baseline_1p25_3p00"])["net_rr"], 2.0)

    def test_rejects_bad_and_duplicate_data(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.csv"
            p.write_text("signal_id,symbol,signal_date,entry_price,atr\n1,COIN,2025-01-03,100,2.5\n", encoding="utf-8")
            out = rr2.audit(p, {("COIN", 2025): 1})
            self.assertEqual(out["input_candidates"], 1)
            self.assertFalse(out["is_realized_backtest"])
            self.assertEqual(out["cohorts"][0]["arms"]["baseline_1p25_3p00"]["accepted"], 0)
            self.assertEqual(out["cohorts"][0]["arms"]["A_1p00_2p50"]["accepted"], 1)
            with self.assertRaisesRegex(ValueError, "cohort mismatch"):
                rr2.audit(p, {("COIN", 2025): 80})
            p.write_text(p.read_text() + "1,COIN,2025-01-06,100,2.5\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                rr2.audit(p)

    def test_invalid_nonfinite_or_empty_input_is_error(self):
        for bad in ("NaN", "0", "-2", "inf"):
            with self.assertRaises(ValueError):
                rr2.assess(float(bad), rr2.ARMS["B_0p75_2p25"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.csv"
            p.write_text("signal_id,symbol,signal_date,entry_price,atr\n")
            with self.assertRaisesRegex(ValueError, "empty candidate"):
                rr2.audit(p)


if __name__ == "__main__":
    unittest.main()
