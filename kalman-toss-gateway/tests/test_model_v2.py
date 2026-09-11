from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.model_v2.build_feature_matrix import asset_feature_frame
from research.model_v2.model_contract import ARTIFACT_SCHEMA, score_row
from research.model_v2.shadow_signal import build_shadow_signal, sha256_file
from research.model_v2.train_candidates import (
    chronological_split,
    train_market,
)


class ModelV2Tests(unittest.TestCase):
    def test_asset_features_are_stationary_contract(self) -> None:
        n = 120
        idx = pd.date_range("2025-01-01", periods=n, freq="D")
        close = 100 + np.linspace(0, 20, n) + np.sin(np.arange(n) / 4)
        raw = pd.DataFrame(
            {
                "timestamp": idx,
                "close": close,
                "volume": np.linspace(1000, 2000, n),
            }
        )
        talib = pd.DataFrame(
            {
                "timestamp": idx,
                "talib_v2_rsi14": np.linspace(40, 65, n),
                "talib_v2_macd": np.linspace(-1, 2, n),
                "talib_v2_macd_hist": np.sin(np.arange(n) / 5),
                "talib_v2_adx14": np.linspace(15, 35, n),
                "talib_v2_atr14": np.linspace(1, 2, n),
                "talib_v2_natr14": np.linspace(1, 3, n),
                "talib_v2_roc10": np.linspace(-5, 8, n),
                "talib_v2_bb_pctb": np.linspace(0.2, 0.8, n),
                "talib_v2_obv": np.cumsum(np.linspace(100, 200, n)),
            }
        )

        features = asset_feature_frame(raw, fetch_key="yf_test", talib=talib)
        self.assertIn("yf_test__ret5", features.columns)
        self.assertIn("yf_test__rsi_centered", features.columns)
        self.assertIn("yf_test__macd_pct", features.columns)
        self.assertNotIn("close", features.columns)
        self.assertGreater(features["yf_test__ret5"].notna().sum(), 100)

    def test_purged_chronological_split(self) -> None:
        n = 300
        frame = pd.DataFrame(
            {
                "as_of": pd.date_range("2025-01-01", periods=n, freq="D"),
                "anchor_close": np.arange(n) + 100,
                "feature_a": np.sin(np.arange(n) / 10),
                "target_forward_return": np.sin(np.arange(n) / 7) / 100,
                "target_label": (np.arange(n) % 3 != 0).astype(float),
            }
        )
        train, validation, test = chronological_split(
            frame,
            horizon=5,
            train_fraction=0.60,
            validation_fraction=0.20,
        )
        self.assertLess(train["as_of"].max(), validation["as_of"].min())
        self.assertLess(validation["as_of"].max(), test["as_of"].min())
        self.assertGreaterEqual(len(validation), 30)
        self.assertGreaterEqual(len(test), 30)

    def test_train_json_model_and_shadow_safety(self) -> None:
        rng = np.random.default_rng(42)
        n = 520
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        f1 = rng.normal(size=n)
        f2 = rng.normal(size=n)
        f3 = rng.normal(size=n)
        latent = 0.9 * f1 - 0.5 * f2 + 0.2 * f3 + rng.normal(scale=0.8, size=n)
        label = (latent > 0).astype(float)
        forward_return = np.where(label > 0, 0.02, -0.015) + rng.normal(scale=0.01, size=n)

        matrix = pd.DataFrame(
            {
                "as_of": dates,
                "anchor_close": 100 * np.cumprod(1 + rng.normal(0.0002, 0.01, size=n)),
                "yf_test__f1": f1,
                "yf_test__f2": f2,
                "group_us__f3": f3,
                "mostly_missing": np.where(np.arange(n) < 450, np.nan, rng.normal(size=n)),
                "target_forward_return": forward_return,
                "target_label": label,
            }
        )

        spec = {
            "version": "kalman_model_v2_test",
            "dataset_version": "matrix_test",
            "feature_set": "feature_test",
            "minimum_feature_coverage": 0.80,
            "maximum_features": 10,
            "train_fraction": 0.60,
            "validation_fraction": 0.20,
            "candidate_c": [0.01, 0.1, 1.0],
            "threshold_grid": [0.50, 0.55, 0.60],
        }
        market_spec = {
            "symbol": "TEST",
            "strategy_version": "KALMAN_V2_TEST_001",
            "horizon_observations": 5,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix_dir = root / "matrices"
            output_dir = root / "models"
            matrix_dir.mkdir(parents=True)
            matrix_path = matrix_dir / "us_matrix.parquet"
            matrix.to_parquet(matrix_path, index=False)
            (matrix_dir / "us_matrix_manifest.json").write_text(
                json.dumps(
                    {
                        "lineage_sha256": "a" * 64,
                        "matrix_sha256": "b" * 64,
                    }
                ),
                encoding="utf-8",
            )

            manifest = train_market(
                market_name="US",
                market_spec=market_spec,
                global_spec=spec,
                matrix_dir=matrix_dir,
                output_dir=output_dir,
            )
            self.assertEqual(manifest["status"], "READY")
            model_path = output_dir / "us" / "model.json"
            artifact = json.loads(model_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["artifact_schema"], ARTIFACT_SCHEMA)
            self.assertNotIn("mostly_missing", artifact["selected_features"])
            self.assertTrue(artifact["shadow_only"])
            self.assertFalse(artifact["live_execution"])

            scored = score_row(matrix.iloc[-1], artifact)
            self.assertGreaterEqual(scored["probability_up"], 0.0)
            self.assertLessEqual(scored["probability_up"], 1.0)

            signal = build_shadow_signal(
                market_name="US",
                matrix=matrix,
                artifact=artifact,
                model_sha256=sha256_file(model_path),
                max_missing_feature_ratio=0.15,
            )
            self.assertEqual(signal["signal"], "SHADOW")
            self.assertFalse(signal["entry_allowed"])
            self.assertFalse(signal["payload"]["allow_trade_shadow"])
            self.assertFalse(signal["payload"]["live_execution"])
            self.assertFalse(signal["payload"]["production_promotion"])


if __name__ == "__main__":
    unittest.main()
