"""Contract tests: Yahoo-origin factor observations never certify raw SIP prices."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from daily20 import load_spec, market_file
from factor_lineage import diagnose, run, VERSION


def yahoo_fixture():
    idx = pd.DatetimeIndex([
        "2026-11-18", "2026-11-19", "2026-11-20",
    ]).tz_localize("America/New_York")
    return pd.DataFrame({
        "Close": [100., 102., 50.],
        "Adj Close": [90., 92., 50.],
        "Dividends": [0., .25, 0.],
        "Stock Splits": [0., 0., 2.],
    }, index=idx)


def cache_fixture():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-11-18", "2026-11-19", "2026-11-20"], utc=True),
        "close": [90., 92., 50.],
        "is_adjusted": [True, True, True],
    })


class FactorLineageTests(unittest.TestCase):
    def test_vendor_ratio_and_event_dates_are_observed_not_certified(self):
        row, csv_bytes = diagnose("SPY", yahoo_fixture(), cache_fixture(), "2026-11-20")
        self.assertEqual(row["status"], "YAHOO_FACTOR_OBSERVED_UNATTESTED")
        self.assertEqual(row["yahoo_dividend_events"], 1)
        self.assertEqual(row["yahoo_split_events"], 1)
        self.assertEqual(row["history_rows"], 3)
        self.assertEqual(row["overlap_days"], 3)
        self.assertEqual(row["latest_abs_diff_usd"], 0.)
        self.assertTrue(row["vendor_observed_not_independently_attested"])
        self.assertIn(b"yahoo_adj_over_close", csv_bytes)
        self.assertIn(b"2026-11-20", csv_bytes)

    def test_existing_adjusted_history_revisions_raise_research_hold(self):
        cached = cache_fixture()
        cached.loc[0, "close"] = 86.
        row, _ = diagnose("QQQ", yahoo_fixture(), cached, "2026-11-20")
        self.assertEqual(row["status"], "YAHOO_ADJUSTED_REPLAY_DRIFT_HOLD")
        self.assertEqual(row["mismatch_gt_half_cent_days"], 1)
        self.assertEqual(row["mismatch_examples"], ["2026-11-18"])

    def test_latest_missing_never_counts_as_verified(self):
        history = yahoo_fixture().iloc[:-1]
        row, _ = diagnose("SPY", history, cache_fixture(), "2026-11-20")
        self.assertEqual(row["status"], "YAHOO_ASOF_SESSION_MISSING_HOLD")
        self.assertIsNone(row["latest_abs_diff_usd"])

    def test_missing_corporate_action_columns_are_not_zero_filled(self):
        with self.assertRaisesRegex(ValueError, "FIELDS_MISSING"):
            diagnose("SPY", yahoo_fixture().drop(columns=["Stock Splits"]),
                     cache_fixture(), "2026-11-20")

    def test_unadjusted_cached_price_rejected(self):
        cache = cache_fixture()
        cache["is_adjusted"] = False
        with self.assertRaisesRegex(ValueError, "MUST_BE_ADJUSTED"):
            diagnose("SPY", yahoo_fixture(), cache, "2026-11-20")

    def test_daily20_run_isolated_25_instruments_no_certification(self):
        spec = load_spec()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sym in spec["core"] + spec["context"]:
                if sym == "^VIX":
                    continue
                path = market_file(root / "market", sym)
                path.parent.mkdir(parents=True, exist_ok=True)
                cache_fixture().to_parquet(path, index=False)
            qc = root / "qc.json"
            qc.write_text(json.dumps({"expected_session": "2026-11-20", "ready": 26,
                                     "status": "READY"}))
            result = run(spec, root / "market", qc, root / "lineage",
                         fetcher=lambda symbol, start, end: yahoo_fixture(),
                         fetched_at="2026-11-21T08:15:00Z")
            self.assertEqual(result["version"], VERSION)
            self.assertEqual((result["required"], result["vendor_history_observed"]), (25, 25))
            self.assertEqual(result["independent_corporate_actions_certified"], 0)
            self.assertEqual(result["finality_verified"], 0)
            self.assertFalse(result["strategy_promoted"])
            self.assertEqual(result["overall_status"], "CORPORATE_ACTION_FACTORS_RESEARCH_HOLD")
            self.assertTrue((root / "lineage" / "qqq.csv.gz").exists())
            self.assertFalse((root / "lineage" / "vix.csv.gz").exists())
            self.assertEqual(len(list((root / "lineage").glob("*.csv.gz"))), 25)
            self.assertTrue((root / "lineage" / "report.json").is_file())

    def test_unrepaired_vs_production_repaired_policy_differences_not_called_vendor_drift(self):
        spec = load_spec()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sym in spec["core"] + spec["context"]:
                if sym != "^VIX":
                    p = market_file(root / "market", sym)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    cache_fixture().to_parquet(p, index=False)
            qc = root / "qc.json"
            qc.write_text(json.dumps({"expected_session": "2026-11-20", "ready": 26, "status": "READY"}))
            def unrepaired(*_):
                raw = yahoo_fixture().copy()
                raw.iloc[0, raw.columns.get_loc("Adj Close")] = 89.
                return raw
            r = run(spec, root / "market", qc, root / "out",
                    fetcher=unrepaired,
                    repaired_fetcher=lambda *a: yahoo_fixture())
            self.assertEqual(r["vendor_history_observed"], 25)
            self.assertEqual(r["unrepaired_source_alignment"], 0)
            self.assertEqual(r["repair_policy_differences"], 25)
            self.assertEqual(r["same_repair_unresolved"], 0)
            self.assertEqual(r["current_source_alignment"], 25)
            self.assertTrue(all(x["status"] == "REPAIR_POLICY_DIFFERENCE_OBSERVED" for x in r["rows"]))
            self.assertEqual(r["finality_verified"], 0)
            self.assertTrue((root / "out" / "qqq_repaired.csv.gz").exists())

    def test_repair_true_still_disagrees_retains_hold(self):
        spec = load_spec()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sym in spec["core"] + spec["context"]:
                if sym != "^VIX":
                    p = market_file(root / "market", sym)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    cache_fixture().to_parquet(p, index=False)
            qc = root / "qc.json"
            qc.write_text(json.dumps({"expected_session": "2026-11-20", "ready": 26, "status": "READY"}))
            def disagree(*_):
                raw = yahoo_fixture().copy()
                raw.iloc[0, raw.columns.get_loc("Adj Close")] = 89.
                return raw
            r = run(spec, root / "market", qc, root / "out",
                    fetcher=disagree, repaired_fetcher=disagree)
            self.assertEqual(r["same_repair_unresolved"], 25)
            self.assertEqual(r["current_source_alignment"], 0)
            self.assertEqual(r["finality_verified"], 0)
            self.assertTrue(all(x["status"] == "SAME_REPAIR_SETTING_MISMATCH_RESEARCH_HOLD"
                                for x in r["rows"]))

    def test_source_unavailable_is_hold_not_no_events(self):
        spec = load_spec()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            qc = root / "qc.json"
            qc.write_text(json.dumps({"expected_session": "2026-11-20", "ready": 26,
                                     "status": "READY"}))
            report = run(spec, root / "absent-market", qc, root / "output",
                         fetcher=lambda *args: yahoo_fixture())
            self.assertEqual(report["vendor_history_observed"], 0)
            self.assertEqual(len(report["rows"]), 25)
            self.assertTrue(all(x["status"] == "SOURCE_OR_SCHEMA_UNAVAILABLE_HOLD"
                                for x in report["rows"]))
            self.assertEqual(report["finality_verified"], 0)


if __name__ == "__main__":
    unittest.main()
