"""Deterministic offline contracts for Daily20, with no web/API access."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from daily20 import (
    build_universe, load_spec, last_completed_nyse,
    audit_all, audit_one, market_file, feature_file, load_bars
)
from train import model_split, nonoverlap, context_frame


class Contracts(unittest.TestCase):
    def test_20_plus_6_and_no_live(self):
        spec = load_spec()
        self.assertEqual((len(spec["core"]), len(spec["context"])), (20, 6))
        self.assertFalse(spec["live_execution"])
        self.assertFalse(spec["write_to_toss"])
        self.assertFalse(spec["write_to_neon"])
        baseline = json.loads(Path("kalman-toss-gateway/config/market-data-v2-universe.json").read_text())
        generated = build_universe(spec, baseline)
        self.assertEqual(len(generated["assets"]), 26)
        self.assertEqual(sum(a["group"] == "DAILY20_CORE" for a in generated["assets"]), 20)
        self.assertTrue(all(a["provider"] == "yfinance" for a in generated["assets"]))
        self.assertTrue(all(a["required"] for a in generated["assets"]))
        self.assertTrue(all(a["adjusted"] == (a["provider_symbol"] != "^VIX")
                            for a in generated["assets"]))

    def test_reject_duplicate_core(self):
        spec = load_spec()
        spec["core"][0] = spec["core"][1]
        with self.assertRaises(ValueError):
            build_universe(spec, {"assets": []}) if len(set(spec["core"] + spec["context"])) != 26 else None
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text(json.dumps(spec))
            with self.assertRaises(ValueError):
                load_spec(p)

    def test_last_completed_market_session(self):
        self.assertEqual(str(last_completed_nyse("2026-11-20T19:00:00Z")), "2026-11-19")
        self.assertEqual(str(last_completed_nyse("2026-11-21T02:40:00Z")), "2026-11-20")

    def test_missing_data_fail_closed(self):
        spec = load_spec()
        universe = build_universe(spec, {"assets": []})
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "manifest.json"
            src.write_text(json.dumps(universe))
            result = audit_all(src, Path(tmp) / "no-market",
                               Path(tmp) / "no-features",
                               Path(tmp) / "qc.json",
                               now="2026-11-21T02:40:00Z")
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["ready"], 0)
            self.assertEqual(len(result["symbols"]), 26)

    def test_single_bar_qc_includes_latest_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            market = Path(tmp) / "market"
            features = Path(tmp) / "features"
            a, b = market_file(market, "SPY"), feature_file(features, "SPY")
            a.parent.mkdir(parents=True)
            b.parent.mkdir(parents=True)
            dates = pd.bdate_range("2025-08-01", periods=300)
            close = 100 + np.arange(300, dtype=float)
            pd.DataFrame({
                "timestamp": dates,
                "symbol": "SPY", "open": close - .25, "high": close + .5,
                "low": close - .5, "close": close, "volume": 100000,
            }).to_parquet(a)
            pd.DataFrame({
                "timestamp": dates,
                "symbol": "SPY", "talib_v2_rsi14": np.linspace(40, 70, 300),
            }).to_parquet(b)
            expected = dates[-1].date()
            self.assertEqual(audit_one("SPY", market, features, expected)["status"], "READY")
            pd.DataFrame({
                "timestamp": dates[:-1],
                "symbol": "SPY", "talib_v2_rsi14": np.linspace(40, 70, 299),
            }).to_parquet(b)
            err = audit_one("SPY", market, features, expected)
            self.assertEqual(err["status"], "BLOCKED")
            self.assertIn("NOT_LATEST_COMPLETED_NYSE_SESSION", err["errors"])

    def test_supervised_label_purge(self):
        idx = pd.bdate_range("2023-12-01", periods=40)
        df = pd.DataFrame(index=idx)
        df["net_return"] = 0.01
        df["exit_date"] = pd.Series(idx, index=idx).shift(-4)
        train, test = model_split(df, 2024)
        self.assertTrue((train["exit_date"] < pd.Timestamp("2024-01-01")).all())
        self.assertTrue((train.index < pd.Timestamp("2024-01-01")).all())
        self.assertTrue((test.index.year == 2024).all())

    def test_nonoverlap_uses_actual_session_not_calendar(self):
        idx = pd.to_datetime(["2026-11-19", "2026-11-20", "2026-11-23", "2026-11-27"])
        frame = pd.DataFrame({
            "entry_date": pd.to_datetime(["2026-11-20", "2026-11-23", "2026-11-24", "2026-11-30"]),
            "exit_date": pd.to_datetime(["2026-11-27", "2026-11-30", "2026-12-01", "2026-12-04"]),
            "net_return": [0.01] * 4, "gross_return": [.012] * 4,
            "spy_above200_lag": [1.] * 4, "prob": [.9] * 4,
        }, index=idx)
        rows = nonoverlap(frame, "LOGISTIC")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entry_date"], "2026-11-20")

    def test_context_one_completed_session_lag(self):
        with tempfile.TemporaryDirectory() as tmp:
            syms = ["SPY", "QQQ", "SMH", "^VIX", "HYG", "LQD", "TLT", "GLD"]
            dates = pd.bdate_range("2025-01-01", periods=220)
            for j, symbol in enumerate(syms):
                target = market_file(tmp, symbol)
                target.parent.mkdir(parents=True, exist_ok=True)
                close = np.arange(220, dtype=float) + 100 + j
                pd.DataFrame({
                    "timestamp": dates, "open": close, "high": close + 1,
                    "low": close - 1, "close": close, "volume": 1000,
                }).to_parquet(target)
            ctx = context_frame(tmp)
            self.assertTrue(pd.isna(ctx["vix_lag"].iloc[0]))
            self.assertEqual(ctx["vix_lag"].iloc[1], 103.0)  # ^VIX is fourth in list
            self.assertTrue(pd.isna(ctx["spy_mom5_lag"].iloc[5]))
            self.assertAlmostEqual(ctx["spy_mom5_lag"].iloc[6], 105 / 100 - 1)


if __name__ == "__main__":
    unittest.main()
