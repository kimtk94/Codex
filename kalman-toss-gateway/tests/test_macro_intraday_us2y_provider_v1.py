from datetime import datetime, timezone
from pathlib import Path

from engine import macro_intraday_us2y_provider_v1 as rates


UTC = timezone.utc


def test_parse_te_intraday_rows_keeps_expected_symbol_and_utc():
    rows = rates.parse_te_intraday_rows(
        [
            {
                "Symbol": "USGG2YR:IND",
                "Date": "2026-10-14T12:29:00",
                "Open": 4.20,
                "High": 4.21,
                "Low": 4.19,
                "Close": 4.20,
            },
            {
                "Symbol": "USGG10YR:IND",
                "Date": "2026-10-14T12:29:00",
                "Close": 5.00,
            },
        ],
        expected_symbol="USGG2YR:IND",
    )
    assert len(rows) == 1
    assert rows[0]["ts"] == datetime(2026, 10, 14, 12, 29, tzinfo=UTC)
    assert rows[0]["close_pct"] == 4.20


def test_reaction_baseline_is_strictly_before_release():
    rows = rates.parse_te_intraday_rows(
        [
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T12:29:00", "Close": 4.20},
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T12:30:00", "Close": 4.25},
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T12:35:00", "Close": 4.30},
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T12:45:00", "Close": 4.35},
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T13:00:00", "Close": 4.40},
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T13:30:00", "Close": 4.45},
        ],
        expected_symbol="USGG2YR:IND",
    )
    out = rates.compute_intraday_reaction(
        rows,
        event_at=datetime(2026, 10, 14, 12, 30, tzinfo=UTC),
        horizons_minutes=[5, 15, 30, 60],
        baseline_max_gap_minutes=5,
        post_max_gap_minutes=2,
    )
    assert out["status"] == "READY"
    assert out["baseline_ts"] == "2026-10-14T12:29:00+00:00"
    assert out["baseline_yield_pct"] == 4.20
    assert abs(out["horizons"]["5m"]["reaction_bps"] - 10.0) < 1e-10
    assert abs(out["horizons"]["15m"]["reaction_bps"] - 15.0) < 1e-10
    assert abs(out["horizons"]["60m"]["reaction_bps"] - 25.0) < 1e-10


def test_reaction_fails_closed_when_pre_release_baseline_is_stale():
    rows = rates.parse_te_intraday_rows(
        [
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T12:20:00", "Close": 4.20},
            {"Symbol": "USGG2YR:IND", "Date": "2026-10-14T12:35:00", "Close": 4.30},
        ],
        expected_symbol="USGG2YR:IND",
    )
    out = rates.compute_intraday_reaction(
        rows,
        event_at=datetime(2026, 10, 14, 12, 30, tzinfo=UTC),
        horizons_minutes=[5],
        baseline_max_gap_minutes=5,
        post_max_gap_minutes=2,
    )
    assert out["status"] == "BASELINE_GAP_EXCEEDED"


def test_fetch_is_quota_safe_outside_event_window(monkeypatch):
    monkeypatch.setenv("TRADING_ECONOMICS_API_KEY", "must-not-be-used")
    cfg = {
        "intraday_us2y": {
            "enabled": True,
            "min_event_age_minutes": 5,
            "max_event_age_minutes": 120,
        }
    }
    out = rates.fetch_intraday_us2y_reaction(
        cfg,
        event_at=datetime(2026, 10, 14, 12, 30, tzinfo=UTC),
        as_of=datetime(2026, 10, 14, 15, 0, tzinfo=UTC),
    )
    assert out["status"] == "OUTSIDE_COLLECTION_WINDOW"


def test_fetch_rejects_missing_credentials_without_network(monkeypatch):
    monkeypatch.delenv("TRADING_ECONOMICS_API_KEY", raising=False)
    cfg = {
        "intraday_us2y": {
            "enabled": True,
            "min_event_age_minutes": 5,
            "max_event_age_minutes": 120,
        }
    }
    out = rates.fetch_intraday_us2y_reaction(
        cfg,
        event_at=datetime(2026, 10, 14, 12, 30, tzinfo=UTC),
        as_of=datetime(2026, 10, 14, 12, 45, tzinfo=UTC),
    )
    assert out["status"] == "UNCONFIGURED_CREDENTIAL"


def test_provider_has_no_execution_side_effects():
    source = Path(rates.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "trade_execution = True"):
        assert forbidden not in source
