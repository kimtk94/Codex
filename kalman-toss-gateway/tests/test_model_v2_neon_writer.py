from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from engine.model_v2_neon_writer import (
    PIPELINE_DB_STATUS,
    assert_latest_success_unchanged,
    build_record,
    load_records,
    normalize_market,
    validate_signal,
)


def _artifact(market: str, symbol: str, strategy: str) -> dict:
    return {
        "artifact_schema": "kalman_logit_json_v1",
        "model_family": "logistic_regression_l2",
        "model_version": "kalman_model_v2_001",
        "dataset_version": "kalman_feature_matrix_v2_001",
        "feature_set": "market_tools_v2_001",
        "market": market,
        "symbol": symbol,
        "strategy_version": strategy,
        "horizon_observations": 5,
        "probability_threshold": 0.55,
        "selected_features": ["a", "b", "c", "d", "e"],
        "imputer_medians": {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0},
        "scaler_mean": {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0},
        "scaler_scale": {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1},
        "coefficients": {"a": 0.1, "b": 0.2, "c": 0.3, "d": 0.4, "e": 0.5},
        "intercept": -0.1,
        "hyperparameters": {"C": 0.1},
        "validation_threshold_metrics": {"balanced_accuracy": 0.61},
        "test_metrics": {"roc_auc": 0.64, "brier": 0.23},
        "candidate_summary": [{"c": 0.1, "validation_roc_auc": 0.63}],
        "training_window": {"refit_through": "2026-08-31T00:00:00+00:00"},
        "sklearn_version": "1.9.1",
        "shadow_only": True,
        "live_execution": False,
        "allow_trade_shadow": False,
    }


def _write_model(path: Path, artifact: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(artifact, ensure_ascii=False, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signal(
    market: str,
    symbol: str,
    strategy: str,
    model_sha: str,
    *,
    allow_trade_shadow: bool = False,
) -> dict:
    return {
        "run_id": f"v2-{market.lower()}-0123456789abcdef",
        "market": market,
        "symbol": symbol,
        "as_of": "2026-09-11T00:00:00+00:00",
        "strategy_version": strategy,
        "signal": "SHADOW",
        "entry_allowed": False,
        "risk_gate": "SHADOW_ONLY",
        "position_state": "FLAT",
        "payload": {
            "model_version": "kalman_model_v2_001",
            "dataset_version": "kalman_feature_matrix_v2_001",
            "feature_set": "market_tools_v2_001",
            "model_family": "logistic_regression_l2",
            "model_sha256": model_sha,
            "probability_up": 0.62,
            "probability_threshold": 0.55,
            "shadow_direction": "BUY",
            "shadow_entry_this_signal": True,
            "data_quality": "PASS",
            "allow_trade_shadow": allow_trade_shadow,
            "live_execution": False,
            "production_promotion": False,
            "neon_write": False,
        },
    }


class ModelV2NeonWriterTests(unittest.TestCase):
    def test_market_mapping_is_schema_compatible(self) -> None:
        self.assertEqual(normalize_market("US"), "US")
        self.assertEqual(normalize_market("KR"), "KR")
        self.assertEqual(normalize_market("BTC"), "CRYPTO")
        self.assertEqual(PIPELINE_DB_STATUS, "ABORTED")


    def test_latest_success_invariant_helper(self) -> None:
        before = {
            "US": ("US-prod", "unified-v1", "2026-09-10", "R5.1", "2026-09-11"),
            "KR": ("KR-prod", "unified-v1", "2026-09-09", "KR-v0.8", "2026-09-10"),
        }
        assert_latest_success_unchanged(before, dict(before))

        after = dict(before)
        after["US"] = (
            "v2-us-unsafe",
            "market-tools-v2/model-shadow-v2_001",
            "2026-09-11",
            "kalman_model_v2_001",
            "2026-09-11",
        )
        with self.assertRaisesRegex(RuntimeError, "v_latest_successful_run"):
            assert_latest_success_unchanged(before, after)

    def test_record_preserves_hard_shadow_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            artifact = _artifact("BTC", "BTC-USD", "KALMAN_V2_BTC_LOGIT_001")
            sha = _write_model(path, artifact)
            signal = _signal(
                "BTC",
                "BTC-USD",
                "KALMAN_V2_BTC_LOGIT_001",
                sha,
            )
            record = build_record(signal, artifact, sha)

        self.assertEqual(record["db_market"], "CRYPTO")
        self.assertEqual(record["model_version"], "kalman_model_v2_001")
        self.assertFalse(record["signal_payload"]["allow_trade_shadow"])
        self.assertFalse(record["signal_payload"]["live_execution"])
        self.assertFalse(record["signal_payload"]["production_promotion"])
        self.assertFalse(record["signal_payload"]["auto_trade_visible"])
        self.assertFalse(record["signal_payload"]["dashboard_snapshot_created"])
        self.assertTrue(record["signal_payload"]["neon_mirrored"])

    def test_allow_trade_shadow_true_is_rejected(self) -> None:
        signal = _signal(
            "US",
            "SPY",
            "KALMAN_V2_US_LOGIT_001",
            "a" * 64,
            allow_trade_shadow=True,
        )
        with self.assertRaisesRegex(ValueError, "allow_trade_shadow"):
            validate_signal(signal)

    def test_load_records_checks_artifact_sha_and_three_markets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_dir = root / "models"
            shadow_file = root / "shadow_signals.json"
            signals = []

            cases = [
                ("US", "SPY", "KALMAN_V2_US_LOGIT_001"),
                ("KR", "KOSPI", "KALMAN_V2_KR_LOGIT_001"),
                ("BTC", "BTC-USD", "KALMAN_V2_BTC_LOGIT_001"),
            ]
            for market, symbol, strategy in cases:
                artifact = _artifact(market, symbol, strategy)
                sha = _write_model(model_dir / market.lower() / "model.json", artifact)
                signals.append(_signal(market, symbol, strategy, sha))

            shadow_file.write_text(json.dumps(signals), encoding="utf-8")
            records = load_records(shadow_file, model_dir)

            self.assertEqual(len(records), 3)
            self.assertEqual(
                [r["db_market"] for r in records],
                ["US", "KR", "CRYPTO"],
            )
            self.assertTrue(all(r["artifact_sha256"] for r in records))


if __name__ == "__main__":
    unittest.main()
