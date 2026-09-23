import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

import r9_2_preboundary_diagnostic as m


def test_preboundary_window_is_frozen():
    assert m.DIAGNOSTIC_START == pd.Timestamp("2026-09-23T13:30:00Z")
    assert m.DIAGNOSTIC_END_EXCLUSIVE == pd.Timestamp("2026-09-24T13:30:00Z")
    assert m.REQUIRED_NEWS_DAY == pd.Timestamp("2026-09-22T00:00:00Z")


def test_diagnostic_identity_is_not_prospective_candidate():
    assert m.DIAGNOSTIC_ID == "R9D_PREBOUNDARY_20260923"
    assert "PREBOUNDARY" in m.DIAGNOSTIC_ID


def test_required_news_day_is_strictly_before_diagnostic_signal_day():
    signal_as_of = m.DIAGNOSTIC_START + pd.Timedelta(1, unit="h")
    news_day = signal_as_of.floor("D") - pd.Timedelta(1, unit="D")
    assert news_day == m.REQUIRED_NEWS_DAY
