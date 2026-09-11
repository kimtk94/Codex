from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from engine.market_data.schema import OHLCV_COLUMNS, canonicalize_ohlcv
from engine.market_data.snapshot import write_snapshot
from engine.market_data.validation import compare_close


class MarketDataV2Tests(unittest.TestCase):
    def _canonical(self, closes: list[float], source: str) -> pd.DataFrame:
        idx = pd.date_range("2026-01-01", periods=len(closes), freq="D")
        raw = pd.DataFrame(
            {
                "Open": closes,
                "High": [x + 1 for x in closes],
                "Low": [x - 1 for x in closes],
                "Close": closes,
                "Volume": [1000] * len(closes),
            },
            index=idx,
        )
        return canonicalize_ohlcv(
            raw,
            symbol="TEST",
            market="US",
            currency="USD",
            source=source,
            column_map={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            },
        )

    def test_canonical_schema(self) -> None:
        frame = self._canonical([100, 101, 102], "provider_a")
        self.assertEqual(list(frame.columns), OHLCV_COLUMNS)
        self.assertEqual(frame["symbol"].unique().tolist(), ["TEST"])
        self.assertEqual(frame["source"].unique().tolist(), ["provider_a"])
        self.assertEqual(frame["close"].tolist(), [100, 101, 102])

    def test_provider_comparison(self) -> None:
        primary = self._canonical([100, 101, 102, 103], "provider_a")
        secondary = self._canonical([100, 101.1, 102.1, 103.1], "provider_b")
        report = compare_close(
            primary,
            secondary,
            primary_name="provider_a",
            secondary_name="provider_b",
        )
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["overlap_rows"], 4)
        self.assertIsNotNone(report["mean_abs_close_relative_diff"])

    def test_atomic_snapshot_and_manifest(self) -> None:
        frame = self._canonical([100, 101, 102], "provider_a")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.parquet"
            manifest = write_snapshot(
                frame,
                path,
                metadata={"provider": "provider_a", "status": "READY"},
            )
            self.assertTrue(path.exists())
            self.assertTrue(path.with_suffix(".metadata.json").exists())
            self.assertEqual(manifest["snapshot_rows"], 3)
            self.assertEqual(len(manifest["snapshot_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
