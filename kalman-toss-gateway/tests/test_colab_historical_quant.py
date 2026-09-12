from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "colab_historical_quant.py"
SPEC = importlib.util.spec_from_file_location("colab_historical_quant", SCRIPT)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_minimum_labeled_rows():
    assert mod.minimum_labeled_rows(504, 63, 126, 5) == 703
    assert mod.minimum_labeled_rows(504, 63, 126, 7) == 707


def test_validate_coverage_accepts_2017_history():
    spec = {
        "markets": {
            "US": {"horizon_observations": 5},
            "KR": {"horizon_observations": 5},
            "BTC": {"horizon_observations": 7},
        }
    }
    coverage = {
        "US": {
            "labeled_rows": 2400,
            "min_labeled_as_of": "2017-01-03T00:00:00+00:00",
        },
        "KR": {
            "labeled_rows": 2300,
            "min_labeled_as_of": "2017-01-02T00:00:00+00:00",
        },
        "BTC": {
            "labeled_rows": 3500,
            "min_labeled_as_of": "2017-01-01T00:00:00+00:00",
        },
    }
    errors = mod.validate_coverage(
        coverage,
        start_date="2017-01-01",
        spec=spec,
        train_obs=504,
        valid_obs=63,
        test_obs=126,
    )
    assert errors == []


def test_find_historical_sources_prefers_v03_features(tmp_path):
    market_root = tmp_path / "Market_Data" / "v2"
    feature_root = tmp_path / "Market_Features" / "v2"
    raw_dir = market_root / "raw" / "historical_2017"
    feature_dir = feature_root / "talib" / "historical_2017"
    raw_dir.mkdir(parents=True)
    feature_dir.mkdir(parents=True)

    raw = raw_dir / "multimarket_raw_2017_present.parquet"
    feature_old = feature_dir / "multimarket_features_2017_present.parquet"
    feature_v03 = feature_dir / "multimarket_features_2017_present_v0_3.parquet"
    raw.write_bytes(b"raw")
    feature_old.write_bytes(b"old")
    feature_v03.write_bytes(b"v03")

    found_raw, found_features = mod.find_historical_sources(
        market_root,
        feature_root,
    )
    assert found_raw == raw
    assert found_features == feature_v03
