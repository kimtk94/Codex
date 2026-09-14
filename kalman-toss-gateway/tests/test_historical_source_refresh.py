from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.shadow_bakeoff.historical_source_refresh import (
    MappingSpec,
    _event_complete,
    refresh_frames,
)


def _historical_price(rows: int = 50) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-07-01", periods=rows, freq="D", tz="UTC")
    close = pd.Series(
        100.0 + np.arange(rows, dtype=float) * 0.5,
        index=dates,
    )
    raw = pd.DataFrame(
        {
            "event_time": dates,
            "available_time": dates,
            "market": ["US"] * rows,
            "indicator_id": ["US_SPY"] * rows,
            "timeframe": ["1D"] * rows,
            "open": close.to_numpy() - 0.2,
            "high": close.to_numpy() + 0.5,
            "low": close.to_numpy() - 0.5,
            "close": close.to_numpy(),
            "volume": np.arange(rows, dtype=float) + 1000,
            "source": ["historical"] * rows,
        }
    )
    features = pd.DataFrame(
        {
            "event_time": dates,
            "available_time": dates,
            "market": ["US"] * rows,
            "indicator_id": ["US_SPY"] * rows,
            "timeframe": ["1D"] * rows,
            "feature_family": ["PRICE"] * rows,
            "RET_1D": close.pct_change(1).to_numpy(),
            "MA20_DIST": (
                close / close.rolling(20, min_periods=20).mean() - 1.0
            ).to_numpy(),
        }
    )
    return raw, features


def _current_snapshot(
    raw: pd.DataFrame,
    *,
    extra_days: int = 2,
) -> pd.DataFrame:
    overlap = raw.tail(30).copy()
    last = pd.Timestamp(raw["event_time"].max())
    extra_dates = pd.date_range(
        last + pd.Timedelta(days=1),
        periods=extra_days,
        freq="D",
        tz="UTC",
    )
    start = float(raw["close"].iloc[-1])
    extra_close = start + 0.5 * np.arange(1, extra_days + 1)
    extra = pd.DataFrame(
        {
            "event_time": extra_dates,
            "open": extra_close - 0.2,
            "high": extra_close + 0.5,
            "low": extra_close - 0.5,
            "close": extra_close,
            "volume": 2000 + np.arange(extra_days),
        }
    )
    out = pd.concat(
        [
            overlap[["event_time", "open", "high", "low", "close", "volume"]],
            extra,
        ],
        ignore_index=True,
    )
    out = out.rename(columns={"event_time": "timestamp"})
    out["source"] = "yfinance"
    return out


def test_event_completion_rejects_same_day_for_24h_asset() -> None:
    assert (
        _event_complete(
            pd.Timestamp("2026-09-14T00:00:00Z"),
            now=pd.Timestamp("2026-09-14T20:00:00Z"),
            timezone="UTC",
            same_day_complete_after=None,
        )
        is False
    )
    assert (
        _event_complete(
            pd.Timestamp("2026-09-13T00:00:00Z"),
            now=pd.Timestamp("2026-09-14T20:00:00Z"),
            timezone="UTC",
            same_day_complete_after=None,
        )
        is True
    )


def test_refresh_appends_only_completed_rows_and_preserves_schema() -> None:
    raw, features = _historical_price()
    current = _current_snapshot(raw, extra_days=2)
    old_max = pd.Timestamp(raw["event_time"].max())

    mapping = MappingSpec(
        indicator_id="US_SPY",
        source_candidates=("raw/yfinance/yf_spy.parquet",),
        timezone="UTC",
        same_day_complete_after=None,
        required_anchor=True,
    )

    # The second new source row is the current UTC day and must be excluded.
    now = old_max + pd.Timedelta(days=2, hours=12)
    raw_out, feat_out, report = refresh_frames(
        raw,
        features,
        source_frames={"US_SPY": current},
        mappings=[mapping],
        now=now,
        parity_min_points=10,
        max_parity_error=1e-8,
        source_overlap_min_points=5,
        max_source_close_relative_error=1e-12,
    )

    assert list(raw_out.columns) == list(raw.columns)
    assert list(feat_out.columns) == list(features.columns)
    assert report["new_raw_rows"] == 1
    assert report["new_feature_rows"] == 1
    assert pd.Timestamp(raw_out["event_time"].max()) == old_max + pd.Timedelta(days=1)
    assert pd.Timestamp(feat_out["event_time"].max()) == old_max + pd.Timedelta(days=1)

    new_feature = feat_out.sort_values("event_time").iloc[-1]
    assert np.isfinite(float(new_feature["RET_1D"]))
    assert np.isfinite(float(new_feature["MA20_DIST"]))


def test_refresh_fails_closed_when_feature_formula_parity_breaks() -> None:
    raw, features = _historical_price()
    features = features.copy()
    features["RET_1D"] = 7.0
    current = _current_snapshot(raw, extra_days=1)

    mapping = MappingSpec(
        indicator_id="US_SPY",
        source_candidates=("raw/yfinance/yf_spy.parquet",),
        timezone="UTC",
        same_day_complete_after=None,
        required_anchor=True,
    )

    with pytest.raises(RuntimeError, match="required anchor refresh failed"):
        refresh_frames(
            raw,
            features,
            source_frames={"US_SPY": current},
            mappings=[mapping],
            now=pd.Timestamp(raw["event_time"].max()) + pd.Timedelta(days=3),
            parity_min_points=10,
            max_parity_error=0.001,
            source_overlap_min_points=5,
            max_source_close_relative_error=1e-12,
        )
