"""Contract-only tests for the read-only fixed-input numerical matrix.

Synthetic bytes here are test fixtures only; CI production workflow uses a
previous real 26-asset main artifact with immutable Actions run ID.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest

from runtime_version_matrix import (
    ASOF, BASELINE_RUN_ID, FAMILIES, PARSER_FIELDS, VERSION,
    compare, parser_fixture, source_index, check_files,
)
from daily20 import load_spec, market_file, feature_file


def fake_worker(variant, *, delta=0.0):
    obs = []
    core = load_spec()["core"]
    for i, symbol in enumerate(core):
        for family in FAMILIES:
            value = (0.3 + (i / 100.0) + delta)
            obs.append({
                "symbol": symbol, "family": family,
                "asof_feature_sha256": "a" * 64,
                "prediction": value, "fold_status": "OOS_EVALUATED",
                "training_rows": 1100, "training_hash": "b" * 64,
                "fitted_model_hash": "c" * 64,
            })
    return {
        "version": VERSION, "variant": variant, "asof_session": ASOF,
        "source_actions_run_id": BASELINE_RUN_ID,
        "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "real_source_manifest_sha256": "d" * 64,
        "native_parser_fixture_sha256": "e" * 64,
        "code_file_sha256": "f" * 64,
        "models_fitted_or_attempted": 40, "assets": 20,
        "package_versions": {
            "numpy": "2.3.5" if variant == "baseline" else "2.4.6",
            "pyarrow": "24.0.0" if variant == "baseline" else "26.0.1",
        },
        "observations": obs,
        "parser_probe": [
            {"engine": "c", "status": "PASS"},
            {"engine": "python", "status": "PASS"},
        ],
        "primary_price_certified": False,
        "causal_model_drift_claimed": False,
    }


class RuntimeVersionMatrixTests(unittest.TestCase):
    def setUp(self):
        self.a = fake_worker("baseline")
        self.b = fake_worker("research")

    def test_same_inputs_same_probs_no_historic_causal_proof(self):
        r = compare(self.a, self.b)
        self.assertEqual(r["compared_models"], 40)
        self.assertEqual(r["compared_core_symbols"], 20)
        self.assertEqual(r["max_probability_delta_pp"], 0)
        self.assertEqual(r["model_probabilities_changed_over_1pp"], 0)
        self.assertEqual(r["experimental_reproducibility"],
                         "RUNTIME_MATRIX_NO_MODEL_DIFFERENCE_OBSERVED")
        self.assertFalse(r["cause_of_historical_20261120_drift_certified"])
        self.assertFalse(r["model_or_trading_rules_changed"])

    def test_numeric_difference_does_not_certify_price_cause(self):
        r = compare(self.a, fake_worker("research", delta=0.012))
        self.assertEqual(r["model_probabilities_changed_over_1pp"], 40)
        self.assertAlmostEqual(r["max_probability_delta_pp"], 1.2)
        self.assertEqual(r["experimental_reproducibility"],
                         "NUMERICAL_RUNTIME_SENSITIVITY_OBSERVED")
        self.assertFalse(r["cause_of_historical_20261120_drift_certified"])

    def test_no_data_drift_allowed(self):
        b = deepcopy(self.b)
        b["real_source_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "MATRIX_NOT_IDENTICAL_INPUT"):
            compare(self.a, b)

    def test_features_must_be_identical(self):
        b = deepcopy(self.b)
        b["observations"][0]["asof_feature_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "MATRIX_INPUT_OR_TRAINING_CHANGED"):
            compare(self.a, b)

    def test_training_input_hash_must_be_identical(self):
        b = deepcopy(self.b)
        b["observations"][0]["training_hash"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "MATRIX_INPUT_OR_TRAINING_CHANGED"):
            compare(self.a, b)

    def test_model_coefficient_hash_changes_are_reported(self):
        b = deepcopy(self.b)
        b["observations"][0]["fitted_model_hash"] = "9" * 64
        r = compare(self.a, b)
        self.assertEqual(r["fitted_model_hash_changed"], 1)
        self.assertEqual(r["model_probabilities_changed_over_1e_8_pp"], 0)

    def test_duplicate_model_key_fails(self):
        b = deepcopy(self.b)
        b["observations"][0] = deepcopy(b["observations"][1])
        with self.assertRaisesRegex(ValueError, "MATRIX_DUPLICATE_MODEL_KEY"):
            compare(self.a, b)

    def test_missing_model_fails(self):
        b = deepcopy(self.b)
        b["observations"].pop()
        with self.assertRaisesRegex(ValueError, "MATRIX_MODEL_KEY_MISSING"):
            compare(self.a, b)

    def test_wrong_versions_cannot_pass(self):
        b = deepcopy(self.b)
        b["package_versions"]["numpy"] = "2.3.5"
        with self.assertRaisesRegex(ValueError, "MATRIX_UNEXPECTED_PINNED_VERSION"):
            compare(self.a, b)

    def test_false_scientific_certificate_rejected(self):
        b = deepcopy(self.b)
        b["causal_model_drift_claimed"] = True
        with self.assertRaisesRegex(ValueError, "MATRIX_FALSE_SCIENTIFIC"):
            compare(self.a, b)

    def test_code_sha_mismatch_rejected(self):
        b = deepcopy(self.b)
        b["code_file_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "MATRIX_NOT_IDENTICAL_INPUT"):
            compare(self.a, b)

    def test_parser_crash_not_turned_into_success(self):
        b = deepcopy(self.b)
        b["parser_probe"][0]["status"] = "CRASH_OR_ERROR_RESEARCH_HOLD"
        r = compare(self.a, b)
        self.assertEqual(r["parser_status_by_variant"]["research"]["c"],
                         "CRASH_OR_ERROR_RESEARCH_HOLD")

    def test_fixture_has_all_20_and_exact_hash(self):
        spec = load_spec()
        with TemporaryDirectory() as d:
            p = Path(d) / "tiny.csv"
            first = parser_fixture(p, spec)
            second = parser_fixture(p, spec)
            self.assertEqual(first, second)
            rows = p.read_text().splitlines()
            self.assertEqual(len(rows), 21)
            self.assertEqual(tuple(rows[0].split(",")), PARSER_FIELDS)

    def test_missing_source_stops_manifest(self):
        with TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "MATRIX_SOURCE_MEMBER_MISSING"):
                source_index(d, load_spec())

    def test_byte_revision_causes_manifest_rejection(self):
        spec = load_spec()
        with TemporaryDirectory() as d:
            root = Path(d)
            for sym in spec["core"] + spec["context"]:
                for file in (market_file(root / "market", sym),
                             feature_file(root / "features", sym)):
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes((sym + ".").encode() * 300)
            original = source_index(root, spec)
            dig = check_files(root, original, spec)
            self.assertEqual(len(dig), 64)
            target = market_file(root / "market", spec["core"][0])
            target.write_bytes(target.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "MATRIX_SOURCE_BYTES_CHANGED"):
                check_files(root, original, spec)


if __name__ == "__main__":
    unittest.main()
