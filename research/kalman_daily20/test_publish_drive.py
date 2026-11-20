"""Offline Drive persistence checks: no OAuth calls, no secrets."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from publish_drive import EXPECTED_TARGETS, build_zip, inspect_payload


def seed(root):
    d, r = Path(root) / "data", Path(root) / "results"
    p = d / "market/raw/yfinance"
    f = d / "features/talib"
    p.mkdir(parents=True)
    f.mkdir(parents=True)
    symbols = [
        "SPY", "QQQ", "QLD", "IWM", "AAPL", "MSFT", "AMZN", "GOOGL",
        "META", "NVDA", "AMD", "AVGO", "MU", "TSLA", "PLTR", "IONQ",
        "COIN", "MSTR", "JPM", "XOM",
        "SMH", "^VIX", "HYG", "LQD", "TLT", "GLD",
    ]
    import re
    key = lambda x: re.sub("[^a-z0-9]+", "_", x.lower()).strip("_")
    for s in symbols:
        (p / ("yf_" + key(s) + ".parquet")).write_bytes(b"PAR1" + b"a" * 128)
        (f / (key("VIX" if s == "^VIX" else s) + ".parquet")).write_bytes(b"PAR1" + b"b" * 128)
    (r / "research").mkdir(parents=True)
    (r / "qc.json").write_text(json.dumps({
        "status": "READY", "required": 26, "ready": 26,
        "expected_session": "2026-11-20",
        "symbols": [{"symbol": x, "status": "READY"} for x in symbols]
    }))
    (r / "research/summary.json").write_text(json.dumps({
        "research_only": True, "live_execution": False,
        "latest_score_count": 20, "total_oos_trades": 1499,
        "version": "kalman-daily20-v1-20261121"
    }))
    (r / "universe-derived.json").write_text(json.dumps({
        "assets": [{"provider_symbol": x} for x in symbols]
    }))
    return d, r


class DrivePublisherTests(unittest.TestCase):
    def test_two_pinned_verified_targets(self):
        self.assertEqual(len(EXPECTED_TARGETS), 2)
        self.assertTrue(all(len(v[0]) >= 20 and v[1].endswith(".zip")
                            for v in EXPECTED_TARGETS.values()))

    def test_validates_26_plus_26_and_zip_manifest(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            mf = inspect_payload(data, results)
            self.assertTrue(mf["research_only"])
            self.assertFalse(mf["production_writes"])
            self.assertEqual(mf["feature_symbols"], 26)
            dst = build_zip(data, Path(root) / "output" / "data.zip", mf)
            with ZipFile(dst) as z:
                self.assertEqual(len(z.namelist()), 53)
                self.assertIsNone(z.testzip())
                payload = json.loads(z.read("drive_manifest.json"))
                self.assertEqual(len(payload["payload_hashes_sha256"]), 52)

    def test_missing_or_incomplete_data_blocks_before_auth(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            (data / "market/raw/yfinance/yf_spy.parquet").unlink()
            with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_PARQUET"):
                inspect_payload(data, results)

    def test_qc_failure_blocks_before_auth(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "qc.json"
            payload = json.loads(path.read_text())
            payload["ready"] = 25
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(RuntimeError, "DATA_QC"):
                inspect_payload(data, results)

    def test_live_flag_fails_closed(self):
        with TemporaryDirectory() as root:
            data, results = seed(root)
            path = results / "research/summary.json"
            payload = json.loads(path.read_text())
            payload["live_execution"] = True
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(RuntimeError, "RESEARCH_ISOLATION"):
                inspect_payload(data, results)


if __name__ == "__main__":
    unittest.main()
