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


def _coverage(rows=2000, year=2017):
    return {
        market: {
            "labeled_rows": rows,
            "min_labeled_as_of": f"{year}-01-03T00:00:00+00:00",
            "max_labeled_as_of": "2026-09-01T00:00:00+00:00",
        }
        for market in mod.MARKETS
    }


def _spec():
    return {
        "markets": {
            "US": {"horizon_observations": 5},
            "KR": {"horizon_observations": 5},
            "BTC": {"horizon_observations": 7},
        }
    }


def test_minimum_labeled_rows():
    assert mod.minimum_labeled_rows(504, 63, 126, 5) == 703
    assert mod.minimum_labeled_rows(504, 63, 126, 7) == 707


def test_validate_coverage_accepts_2017_history():
    errors = mod.validate_coverage(
        _coverage(),
        start_date="2017-01-01",
        spec=_spec(),
        train_obs=504,
        valid_obs=63,
        test_obs=126,
    )
    assert errors == []


def test_validate_coverage_rejects_short_or_late_history():
    coverage = _coverage()
    coverage["US"] = {
        "labeled_rows": 100,
        "min_labeled_as_of": "2026-01-01T00:00:00+00:00",
        "max_labeled_as_of": "2026-09-01T00:00:00+00:00",
    }
    errors = mod.validate_coverage(
        coverage,
        start_date="2017-01-01",
        spec=_spec(),
        train_obs=504,
        valid_obs=63,
        test_obs=126,
    )
    assert any("labeled_rows" in item for item in errors)
    assert any("earliest labeled year" in item for item in errors)


def test_find_historical_inputs_prefers_v0_3(tmp_path):
    market_root = tmp_path / "Market_Data" / "v2"
    feature_root = tmp_path / "Market_Features" / "v2"
    raw_dir = market_root / "raw" / "historical_2017"
    feat_dir = feature_root / "talib" / "historical_2017"
    raw_dir.mkdir(parents=True)
    feat_dir.mkdir(parents=True)

    old_raw = raw_dir / "multimarket_raw_2017_present.parquet"
    warmup = raw_dir / "multimarket_raw_2016_warmup_2017_present_v0_3.parquet"
    old_features = feat_dir / "multimarket_features_2017_present.parquet"
    v03_features = feat_dir / "multimarket_features_2017_present_v0_3.parquet"
    for path in (old_raw, warmup, old_features, v03_features):
        path.write_bytes(b"x")

    raw, features = mod.find_historical_inputs(market_root, feature_root)
    assert raw == warmup
    assert features == v03_features
