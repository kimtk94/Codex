from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from research.shadow_bakeoff.historical_source_refresh import (
    MappingSpec,
    _atomic_write_pair,
    _candidate_formulas,
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


def test_refresh_ignores_non_daily_rows_for_daily_bridge() -> None:
    raw, features = _historical_price(rows=80)

    raw_4h = raw.tail(30).copy()
    raw_4h["event_time"] = (
        pd.to_datetime(raw_4h["event_time"], utc=True)
        + pd.Timedelta(hours=4)
    )
    raw_4h["available_time"] = raw_4h["event_time"]
    raw_4h["timeframe"] = "4H"
    for column in ("open", "high", "low", "close"):
        raw_4h[column] = pd.to_numeric(
            raw_4h[column],
            errors="coerce",
        ) * 10.0

    feat_4h = features.tail(30).copy()
    feat_4h["event_time"] = (
        pd.to_datetime(feat_4h["event_time"], utc=True)
        + pd.Timedelta(hours=4)
    )
    feat_4h["available_time"] = feat_4h["event_time"]
    feat_4h["timeframe"] = "4H"
    feat_4h["RET_1D"] = 7.0
    feat_4h["MA20_DIST"] = 7.0

    raw_mixed = pd.concat([raw, raw_4h], ignore_index=True)
    features_mixed = pd.concat(
        [features, feat_4h],
        ignore_index=True,
    )

    current = _current_snapshot(raw, extra_days=2)
    old_daily_max = pd.Timestamp(raw["event_time"].max())

    mapping = MappingSpec(
        indicator_id="US_SPY",
        source_candidates=(
            "raw/yfinance/yf_spy.parquet",
        ),
        timezone="UTC",
        same_day_complete_after=None,
        required_anchor=True,
    )

    raw_out, feat_out, report = refresh_frames(
        raw_mixed,
        features_mixed,
        source_frames={"US_SPY": current},
        mappings=[mapping],
        now=old_daily_max + pd.Timedelta(
            days=2,
            hours=12,
        ),
        parity_min_points=10,
        max_parity_error=1e-8,
        source_overlap_min_points=5,
        max_source_close_relative_error=1e-12,
    )

    assert report["new_raw_rows"] == 1
    assert report["new_feature_rows"] == 1

    expected_event = old_daily_max + pd.Timedelta(days=1)
    appended_raw = raw_out.loc[
        pd.to_datetime(
            raw_out["event_time"],
            utc=True,
        ).eq(expected_event)
        & raw_out["timeframe"].astype(str).eq("1D")
    ]
    appended_feat = feat_out.loc[
        pd.to_datetime(
            feat_out["event_time"],
            utc=True,
        ).eq(expected_event)
        & feat_out["timeframe"].astype(str).eq("1D")
    ]

    assert len(appended_raw) == 1
    assert len(appended_feat) == 1
    assert np.isfinite(
        float(appended_feat["RET_1D"].iloc[0])
    )
    assert np.isfinite(
        float(appended_feat["MA20_DIST"].iloc[0])
    )


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

def test_candidate_formulas_include_exact_historical_change_vol20_and_rv20() -> None:
    rows = 80
    index = pd.date_range(
        "2026-01-01",
        periods=rows,
        freq="D",
        tz="UTC",
    )

    # Nonlinear series so competing volatility formulas do not
    # accidentally collapse to the same result.
    x = np.arange(rows, dtype=float)

    close = pd.Series(
        100.0
        + 0.35 * x
        + 2.0 * np.sin(x / 3.0)
        + 0.7 * np.cos(x / 7.0),
        index=index,
    )

    frame = pd.DataFrame(
        {
            "close": close.to_numpy(),
        },
        index=index,
    )

    change_candidates = _candidate_formulas(
        frame,
        "CHANGE_VOL20",
    )

    expected_change_vol20 = (
        close.diff()
        .rolling(20, min_periods=20)
        .std(ddof=0)
    )

    assert "change_vol20_diff_ddof0" in change_candidates

    np.testing.assert_allclose(
        change_candidates[
            "change_vol20_diff_ddof0"
        ].to_numpy(),
        expected_change_vol20.to_numpy(),
        rtol=0.0,
        atol=1e-12,
        equal_nan=True,
    )

    rv_candidates = _candidate_formulas(
        frame,
        "RV20",
    )

    logret = np.log(
        close / close.shift(1)
    )

    expected_rv20 = (
        logret
        .rolling(20, min_periods=20)
        .std(ddof=0)
        * np.sqrt(252.0)
    )

    assert "rv20_log_ann_ddof0" in rv_candidates

    np.testing.assert_allclose(
        rv_candidates[
            "rv20_log_ann_ddof0"
        ].to_numpy(),
        expected_rv20.to_numpy(),
        rtol=0.0,
        atol=1e-12,
        equal_nan=True,
    )


def test_atomic_write_pair_preserves_exact_arrow_schema(tmp_path) -> None:
    raw_path = tmp_path / "raw.parquet"
    feature_path = tmp_path / "features.parquet"
    backup_dir = tmp_path / "backup"

    raw_schema = pa.schema(
        [
            pa.field(
                "event_time",
                pa.timestamp("ns", tz="UTC"),
            ),
            pa.field("market", pa.string()),
            pa.field("source", pa.string()),
            pa.field(
                "source_updated_at",
                pa.timestamp("ns", tz="UTC"),
            ),
            pa.field("value", pa.float64()),
        ],
        metadata={
            b"schema_version": b"raw_exact_v1",
        },
    )

    feature_schema = pa.schema(
        [
            pa.field(
                "event_time",
                pa.timestamp("ns", tz="UTC"),
            ),
            pa.field("market", pa.string()),
            pa.field("source", pa.string()),
            pa.field("feature_family", pa.string()),
            pa.field("RAW_VALUE", pa.float64()),
        ],
        metadata={
            b"schema_version": b"feature_exact_v1",
        },
    )

    raw_seed = pa.Table.from_pydict(
        {
            "event_time": [
                pd.Timestamp(
                    "2026-09-11T00:00:00Z"
                )
            ],
            "market": ["KR"],
            "source": ["historical"],
            "source_updated_at": [
                pd.Timestamp(
                    "2026-09-11T06:35:00Z"
                )
            ],
            "value": [6909.91],
        },
        schema=raw_schema,
    )

    feature_seed = pa.Table.from_pydict(
        {
            "event_time": [
                pd.Timestamp(
                    "2026-09-11T00:00:00Z"
                )
            ],
            "market": ["KR"],
            "source": ["historical"],
            "feature_family": ["PRICE"],
            "RAW_VALUE": [6909.91],
        },
        schema=feature_schema,
    )

    pq.write_table(raw_seed, raw_path)
    pq.write_table(feature_seed, feature_path)

    raw_out = pd.DataFrame(
        {
            "event_time": pd.to_datetime(
                [
                    "2026-09-11T00:00:00Z",
                    "2026-09-14T00:00:00Z",
                ],
                utc=True,
            ),
            "market": ["KR", "KR"],
            "source": [
                "historical",
                "FinanceDataReader",
            ],
            "source_updated_at": pd.to_datetime(
                [
                    "2026-09-11T06:35:00Z",
                    "2026-09-14T10:23:26Z",
                ],
                utc=True,
            ),
            "value": [
                6909.91,
                6684.37,
            ],
        }
    )

    feature_out = pd.DataFrame(
        {
            "event_time": pd.to_datetime(
                [
                    "2026-09-11T00:00:00Z",
                    "2026-09-14T00:00:00Z",
                ],
                utc=True,
            ),
            "market": ["KR", "KR"],
            "source": [
                "historical",
                "DERIVED:KR_KOSPI:HIST_REFRESH_V1",
            ],
            "feature_family": [
                "PRICE",
                "PRICE",
            ],
            "RAW_VALUE": [
                6909.91,
                6684.37,
            ],
        }
    )

    backups = _atomic_write_pair(
        raw_out,
        feature_out,
        raw_path=raw_path,
        feature_path=feature_path,
        backup_dir=backup_dir,
    )

    assert pq.read_schema(raw_path).equals(
        raw_schema,
        check_metadata=True,
    )

    assert pq.read_schema(feature_path).equals(
        feature_schema,
        check_metadata=True,
    )

    assert (
        pq.ParquetFile(raw_path).metadata.num_rows
        == 2
    )

    assert (
        pq.ParquetFile(feature_path).metadata.num_rows
        == 2
    )

    assert pq.read_schema(
        backups["raw_backup"]
    ).equals(
        raw_schema,
        check_metadata=True,
    )

    assert pq.read_schema(
        backups["feature_backup"]
    ).equals(
        feature_schema,
        check_metadata=True,
    )

