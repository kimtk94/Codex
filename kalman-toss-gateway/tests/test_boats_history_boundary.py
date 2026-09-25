from __future__ import annotations

import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.boats_history_boundary import (
    _month_windows,
)


def test_month_windows_cover_requested_range_without_gaps():
    start = pd.Timestamp("2025-01-15T00:00:00Z")
    end = pd.Timestamp("2025-03-10T00:00:00Z")

    windows = _month_windows(start, end)

    assert windows == [
        (
            pd.Timestamp("2025-01-15T00:00:00Z"),
            pd.Timestamp("2025-02-01T00:00:00Z"),
        ),
        (
            pd.Timestamp("2025-02-01T00:00:00Z"),
            pd.Timestamp("2025-03-01T00:00:00Z"),
        ),
        (
            pd.Timestamp("2025-03-01T00:00:00Z"),
            pd.Timestamp("2025-03-10T00:00:00Z"),
        ),
    ]


def test_month_windows_accept_naive_timestamps_as_utc():
    windows = _month_windows(
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-02-01"),
    )
    assert windows == [
        (
            pd.Timestamp("2026-01-01T00:00:00Z"),
            pd.Timestamp("2026-02-01T00:00:00Z"),
        )
    ]
