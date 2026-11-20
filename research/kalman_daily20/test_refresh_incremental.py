"""Offline integration checks for verified Drive cache and incremental merging."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import numpy as np
import pandas as pd

from daily20 import build_universe, load_spec, market_file
from publish_drive import build_zip
from refresh_incremental import (
    combine_history, incremental_refresh, overlap_diagnostics,
    read_verified_cache, validate_old_frame, MAX_OVERLAP_MEDIAN_DRIFT
)
from secondary_qc import compare_return_series


class FakeProvider:
    def __init__(self, frames):
        self.frames = frames
        self.requests = []

    def fetch(self, req):
        self.requests.append(req)
        df = self.frames[req.symbol]
        started = pd.Timestamp(req.start)
        end = pd.Timestamp(req.end)
        frame = df[
            (pd.to_datetime(df["timestamp"]) >= started)
            & (pd.to_datetime(df["timestamp"]) < end)
        ].copy()
        from engine.market_data.base import ProviderResult
        return ProviderResult(frame, {"provider": "fake-for-contracts", "status": "READY"})


def fixtures(root):
    spec = load_spec()
    canonical = json.loads(Path("kalman-toss-gateway/config/market-data-v2-universe.json").read_text())
    universe = build_universe(spec, canonical)
    root = Path(root)
    folder = root / "data"
    all_frames = {}
    sessions = pd.bdate_range(end="2026-11-19", periods=330)
    for idx, item in enumerate(universe["assets"]):
        name = item["symbol"]
        close = 100.0 + idx + np.arange(len(sessions)) / 20.0
        df = pd.DataFrame({
            "timestamp": sessions, "market": "US", "symbol": name,
            "open": close - .1, "high": close + .25, "low": close - .25,
            "close": close, "adj_close": close, "volume": 1000,
            "currency": "USD", "source": "yfinance",
            "source_asof": sessions, "retrieved_at": "2026-11-20T00:00:00Z",
            "is_adjusted": bool(item["adjusted"]),
        })
        folder_name = folder / "market/raw/yfinance" / (item["key"] + ".parquet")
        folder_name.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(folder_name, index=False)
        feat_path = folder / "features/talib"
        feat_path.mkdir(parents=True, exist_ok=True)
        from daily20 import feature_file
        pd.DataFrame({"timestamp": sessions, "symbol": name, "talib_v2_rsi14": 50.0}).to_parquet(
            feature_file(folder / "features", name), index=False
        )
        new_day = pd.Timestamp("2026-11-20")
        new = df.iloc[[-1]].copy()
        new["timestamp"] = new_day
        new["source_asof"] = new_day
        new["open"] += 0.02
        new["high"] += 0.02
        new["low"] += 0.02
        new["close"] += 0.02
        new["adj_close"] += 0.02
        all_frames[name] = pd.concat([df, new], ignore_index=True)
    manifest = {
        "format": "kalman-daily20-drive-v1", "research_only": True,
        "production_writes": False, "raw_symbols": 26, "feature_symbols": 26,
        "universe_version": spec["version"],
        "data_expected_last_closed_xnys": "2026-11-19",
    }
    archive = build_zip(folder, root / "daily20_data_latest.zip", manifest)
    universe_file = root / "universe.json"
    universe_file.write_text(json.dumps(universe))
    return universe, universe_file, archive.read_bytes(), all_frames


class IncrementalContracts(unittest.TestCase):
    def test_incremental_26_history_reuse_and_update(self):
        with TemporaryDirectory() as tmp:
            universe, path, raw_zip, frames = fixtures(tmp)
            prior, old_map = read_verified_cache(raw_zip, {x["key"] for x in universe["assets"]})
            self.assertEqual(len(old_map), 26)
            self.assertEqual(prior["data_expected_last_closed_xnys"], "2026-11-19")
            fake = FakeProvider(frames)
            report = incremental_refresh(path, Path(tmp) / "newmarket",
                                         "2026-11-21", raw_zip, provider=fake)
            self.assertEqual(report["mode"], "INCREMENTAL")
            self.assertEqual(len(fake.requests), 26)
            self.assertEqual({r.start for r in fake.requests}, {"2026-10-04"})
            merged = pd.read_parquet(market_file(Path(tmp) / "newmarket", "SPY"))
            self.assertEqual(len(merged), 331)
            self.assertEqual(str(pd.Timestamp(merged.timestamp.max()).date()), "2026-11-20")
            self.assertEqual(merged["symbol"].nunique(), 1)

    def test_detect_corporate_action_history_revisions(self):
        dates = pd.bdate_range("2026-09-01", periods=31)
        original = pd.DataFrame({"timestamp": dates, "open": 100., "high": 101.,
                                 "low": 99., "close": 100.})
        changed = original.copy()
        for c in ("open", "high", "low", "close"):
            changed[c] *= .98
        detected = overlap_diagnostics(original, changed)
        self.assertTrue(detected["revision"])
        self.assertGreater(detected["median_abs_reprice"], MAX_OVERLAP_MEDIAN_DRIFT)

    def test_zero_drift_and_duplicate_overlap_resolved(self):
        dates = pd.bdate_range("2026-09-01", periods=31)
        old = pd.DataFrame({"timestamp": dates, "symbol": "SPY", "open": 100.,
                            "high": 101., "low": 99., "close": 100.})
        fresh = old.tail(20).copy()
        fresh.loc[fresh.index[-1], "close"] = 100.0001
        self.assertFalse(overlap_diagnostics(old, fresh)["revision"])
        merged = combine_history(old, fresh)
        self.assertEqual(len(merged), 31)
        self.assertEqual(float(merged["close"].iloc[-1]), 100.0001)

    def test_corrupt_sha_manifest_blocks(self):
        with TemporaryDirectory() as tmp:
            universe, path, raw_zip, _ = fixtures(tmp)
            from io import BytesIO
            buf = BytesIO()
            with ZipFile(BytesIO(raw_zip)) as r, ZipFile(buf, "w") as z:
                for name in r.namelist():
                    payload = r.read(name)
                    if name.endswith("yf_spy.parquet"):
                        payload = b"tampered-content"
                    z.writestr(name, payload)
            with self.assertRaisesRegex(RuntimeError, "CACHE_HASH_MISMATCH"):
                read_verified_cache(buf.getvalue(), {x["key"] for x in universe["assets"]})

    def test_not_really_independent_source_diagnostic(self):
        dates = pd.bdate_range("2026-09-01", periods=30)
        series = pd.Series(np.arange(30) + 100., index=dates)
        ok = compare_return_series(series, series.copy())
        self.assertEqual(ok["status"], "ALIGNED")
        error = compare_return_series(series, pd.Series(
            (np.arange(30) + 100.) * (1 + np.linspace(0, .4, 30)), index=dates))
        self.assertEqual(error["status"], "DISAGREEMENT")


if __name__ == "__main__":
    unittest.main()
