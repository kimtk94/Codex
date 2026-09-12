from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "colab_historical_quant.py"
SPEC = importlib.util.spec_from_file_location("colab_historical_quant", SCRIPT)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_minimum_labeled_rows():
    assert mod.minimum_labeled_rows(504, 63, 126, 5) == 703
    assert mod.minimum_labeled_rows(504, 63, 126, 14) == 721


def test_validate_coverage_accepts_2017_history():
    spec = {
        "markets": {
            "US": {"horizon_observations": 5},
            "KR": {"horizon_observations": 5},
            "BTC": {"horizon_observations": 14},
        }
    }
    coverage = {
        "US": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-01T00:00:00+00:00"},
        "KR": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-01T00:00:00+00:00"},
        "BTC": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-01T00:00:00+00:00"},
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


def test_validate_coverage_rejects_short_or_late_history():
    spec = {
        "markets": {
            "US": {"horizon_observations": 5},
            "KR": {"horizon_observations": 5},
            "BTC": {"horizon_observations": 14},
        }
    }
    coverage = {
        "US": {"labeled_rows": 100, "min_labeled_as_of": "2026-01-01T00:00:00+00:00"},
        "KR": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-01T00:00:00+00:00"},
        "BTC": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-01T00:00:00+00:00"},
    }
    errors = mod.validate_coverage(
        coverage,
        start_date="2017-01-01",
        spec=spec,
        train_obs=504,
        valid_obs=63,
        test_obs=126,
    )
    assert any("labeled_rows" in item for item in errors)
    assert any("earliest labeled year" in item for item in errors)
