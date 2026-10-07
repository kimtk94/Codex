from __future__ import annotations

import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.r5_universe_audit import audit


def test_constant_universe_without_pit_columns_is_high_risk(tmp_path):
    p = tmp_path / "rankings.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2023-01-03T14:30:00Z", "2023-01-03T14:30:00Z", "2024-01-03T14:30:00Z", "2024-01-03T14:30:00Z"],
                utc=True,
            ),
            "symbol": ["A", "B", "A", "B"],
        }
    ).to_parquet(p, index=False)
    got = audit(p)
    assert got["constant_membership"] is True
    assert got["distinct_monthly_membership_sets"] == 1
    assert got["survivorship_risk"] == "HIGH"


def test_membership_change_is_not_labeled_constant(tmp_path):
    p = tmp_path / "rankings.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2023-01-03T14:30:00Z", "2023-01-03T14:30:00Z", "2024-01-03T14:30:00Z", "2024-01-03T14:30:00Z"],
                utc=True,
            ),
            "symbol": ["A", "B", "A", "C"],
        }
    ).to_parquet(p, index=False)
    got = audit(p)
    assert got["constant_membership"] is False
    assert got["distinct_monthly_membership_sets"] == 2
    assert got["survivorship_risk"] == "REVIEW"
