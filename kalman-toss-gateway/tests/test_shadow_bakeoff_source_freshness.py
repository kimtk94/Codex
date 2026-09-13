from __future__ import annotations

import pandas as pd

from research.shadow_bakeoff.source_freshness import inspect_source_freshness


def _raw(us: str, kr: str, btc: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"indicator_id": "US_SPY", "event_time": us},
            {"indicator_id": "KR_KOSPI", "event_time": kr},
            {"indicator_id": "BTC_BTCUSD", "event_time": btc},
        ]
    )


def _features(ts: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "indicator_id": "US_SPY",
                "available_time": ts,
            }
        ]
    )


def test_source_freshness_waits_until_all_anchors_and_features_advance(tmp_path) -> None:
    raw_path = tmp_path / "raw.parquet"
    feature_path = tmp_path / "features.parquet"

    _raw(
        "2026-09-12T00:00:00Z",
        "2026-09-11T00:00:00Z",
        "2026-09-13T00:00:00Z",
    ).to_parquet(raw_path, index=False)
    _features("2026-09-13T00:00:00Z").to_parquet(feature_path, index=False)

    payload = inspect_source_freshness(
        raw_path=raw_path,
        feature_path=feature_path,
        seed_end=pd.Timestamp("2026-09-11T00:00:00Z"),
    )

    assert payload["status"] == "WAITING_SOURCE_REFRESH"
    assert payload["anchor_ready"]["US"] is True
    assert payload["anchor_ready"]["KR"] is False
    assert payload["anchor_ready"]["BTC"] is True
    assert payload["feature_ready"] is True


def test_source_freshness_ready_only_after_all_sources_advance(tmp_path) -> None:
    raw_path = tmp_path / "raw.parquet"
    feature_path = tmp_path / "features.parquet"

    _raw(
        "2026-09-12T00:00:00Z",
        "2026-09-12T00:00:00Z",
        "2026-09-13T00:00:00Z",
    ).to_parquet(raw_path, index=False)
    _features("2026-09-12T00:00:00Z").to_parquet(feature_path, index=False)

    payload = inspect_source_freshness(
        raw_path=raw_path,
        feature_path=feature_path,
        seed_end=pd.Timestamp("2026-09-11T00:00:00Z"),
    )

    assert payload["status"] == "READY"
    assert all(payload["anchor_ready"].values())
    assert payload["feature_ready"] is True
    assert payload["live_execution"] is False
    assert payload["toss_execution"] is False
    assert payload["neon_write"] is False
    assert payload["production_write"] is False
