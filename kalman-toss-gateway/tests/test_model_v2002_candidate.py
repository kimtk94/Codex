from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from engine.features_v2_002.registry import FEATURE_SET
from engine.features_v2_002.talib_features import build_talib_features
from research.model_v2_002.model_contract import ARTIFACT_SCHEMA, score_row
from research.model_v2_002.train_candidates import train_market, validation_subsplit


class ModelV2002CandidateTests(unittest.TestCase):
    def test_sparse_gap_feature_builder_recovers_rsi_without_price_fill(self) -> None:
        n = 160
        idx = pd.date_range("2026-01-01", periods=n, freq="D")
        close = 20 + np.linspace(0, 8, n) + np.sin(np.arange(n) / 4)
        frame = pd.DataFrame(
            {
                "timestamp": idx,
                "symbol": "VIX",
                "open": close - 0.2,
                "high": close + 0.8,
                "low": close - 0.8,
                "close": close,
                "adj_close": close,
                "volume": np.linspace(1000, 2000, n),
            }
        )
        gap_rows = [5, 40, 90]
        frame.loc[gap_rows, ["open", "high", "low", "close", "adj_close"]] = np.nan

        features = build_talib_features(frame)
        self.assertEqual(features["feature_set"].iloc[-1], FEATURE_SET)
        self.assertGreater(int(features["talib_v2_rsi14"].notna().sum()), 100)
        for row in gap_rows:
            self.assertTrue(pd.isna(features.loc[row, "talib_v2_rsi14"]))

    def test_validation_subsplit_is_chronological_and_separated(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of": pd.date_range("2025-01-01", periods=150, freq="D"),
                "target_label": np.arange(150) % 2,
            }
        )
        tune, calibration, threshold = validation_subsplit(
            frame,
            horizon=5,
            ratios={"tune": 0.34, "calibration": 0.33, "threshold": 0.33},
        )
        self.assertLess(tune["as_of"].max(), calibration["as_of"].min())
        self.assertLess(calibration["as_of"].max(), threshold["as_of"].min())
        self.assertGreaterEqual(len(tune), 25)
        self.assertGreaterEqual(len(calibration), 25)
        self.assertGreaterEqual(len(threshold), 25)

    def test_train_calibrated_candidate_artifact(self) -> None:
        rng = np.random.default_rng(42)
        n = 760
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        features = {f"f{i}": rng.normal(size=n) for i in range(1, 25)}
        latent = (
            1.0 * features["f1"]
            - 0.7 * features["f2"]
            + 0.5 * features["f3"]
            + rng.normal(scale=1.0, size=n)
        )
        label = (latent > 0).astype(float)
        forward_return = np.where(label > 0, 0.015, -0.012) + rng.normal(0, 0.008, n)
        matrix = pd.DataFrame(
            {
                "as_of": dates,
                "anchor_close": 100 * np.cumprod(1 + rng.normal(0.0002, 0.01, n)),
                **features,
                "target_forward_return": forward_return,
                "target_label": label,
            }
        )

        spec = {
            "version": "kalman_model_v2_002_test",
            "dataset_version": "matrix_v2_002_test",
            "feature_set": "market_tools_v2_002_test",
            "minimum_feature_coverage": 0.80,
            "candidate_feature_counts": [8, 16],
            "candidate_c": [0.01, 0.1],
            "candidate_class_weight": [None, "balanced"],
            "train_fraction": 0.60,
            "validation_fraction": 0.20,
            "validation_subsplit_ratios": {
                "tune": 0.34,
                "calibration": 0.33,
                "threshold": 0.33,
            },
            "threshold_grid": [0.50, 0.55, 0.60],
            "shadow_quality_gate": {
                "minimum_test_rows": 100,
                "minimum_test_roc_auc": 0.52,
                "minimum_brier_skill": 0.0,
                "minimum_log_loss_skill": 0.0,
            },
        }
        market_spec = {
            "symbol": "TEST",
            "strategy_version": "KALMAN_V2_002_TEST",
            "horizon_observations": 5,
        }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            matrix_dir = root / "matrices"
            output_dir = root / "models"
            matrix_dir.mkdir(parents=True)
            matrix.to_parquet(matrix_dir / "us_matrix.parquet", index=False)
            (matrix_dir / "us_matrix_manifest.json").write_text(
                json.dumps({"lineage_sha256": "a" * 64, "matrix_sha256": "b" * 64}),
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
            artifact = json.loads((output_dir / "us/model.json").read_text())
            self.assertEqual(artifact["artifact_schema"], ARTIFACT_SCHEMA)
            self.assertEqual(artifact["probability_calibration"]["method"], "platt")
            self.assertTrue(artifact["shadow_only"])
            self.assertTrue(artifact["research_candidate"])
            self.assertFalse(artifact["live_execution"])
            self.assertIn("brier_skill", artifact["test_metrics"])
            self.assertIn("log_loss_skill", artifact["test_metrics"])
            self.assertLessEqual(len(artifact["selected_features"]), 16)

            scored = score_row(matrix.iloc[-1], artifact)
            self.assertGreaterEqual(scored["probability_up"], 0.0)
            self.assertLessEqual(scored["probability_up"], 1.0)
            self.assertIn("raw_probability_up", scored)


if __name__ == "__main__":
    unittest.main()
