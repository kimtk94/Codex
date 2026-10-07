import base64
import json
import zlib
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


def test_missing_credentials_fail_closed_when_public_fallback_disabled(monkeypatch):
    monkeypatch.delenv("TRADING_ECONOMICS_API_KEY", raising=False)
    cfg = {
        "intraday_us2y": {
            "enabled": True,
            "min_event_age_minutes": 5,
            "max_event_age_minutes": 120,
            "public_chart_fallback": {"enabled": False},
        }
    }
    out = rates.fetch_intraday_us2y_reaction(
        cfg,
        event_at=datetime(2026, 10, 14, 12, 30, tzinfo=UTC),
        as_of=datetime(2026, 10, 14, 12, 45, tzinfo=UTC),
    )
    assert out["status"] == "PUBLIC_CHART_FALLBACK_DISABLED"
    assert out["primary_provider_status"] == "UNCONFIGURED_CREDENTIAL"


def test_provider_has_no_execution_side_effects():
    source = Path(rates.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "trade_execution = True"):
        assert forbidden not in source


def _encode_public_payload(obj, key="tradingeconomics-charts-core-api-key"):
    raw = json.dumps(obj, separators=(",", ":")).encode()
    compressor = zlib.compressobj(wbits=zlib.MAX_WBITS | 16)
    gz = compressor.compress(raw) + compressor.flush()
    kb = key.encode()
    xored = bytes(value ^ kb[i % len(kb)] for i, value in enumerate(gz))
    return base64.b64encode(xored).decode()


def test_public_chart_payload_decodes_and_parses_5m_rows():
    payload = {
        "cacheTime": "2026-10-07T17:40:00+00:00",
        "series": [
            {
                "symbol": "USGG2YR:IND",
                "data": [
                    [1791408000, 4.80, 0.0, 0.0, 4.79, 4.81, 4.79, 4.80],
                    [1791408300, 4.82, 0.0, 0.0, 4.80, 4.82, 4.80, 4.82],
                ],
            }
        ],
    }
    encoded = _encode_public_payload(payload)
    decoded = rates.decode_public_chart_payload(
        encoded,
        obfuscation_key="tradingeconomics-charts-core-api-key",
    )
    rows = rates.parse_public_chart_rows(
        decoded,
        expected_symbol="USGG2YR:IND",
    )
    assert len(rows) == 2
    assert rows[0]["close_pct"] == 4.80
    assert rows[1]["close_pct"] == 4.82


def test_missing_api_key_uses_labeled_public_fallback(monkeypatch):
    monkeypatch.delenv("TRADING_ECONOMICS_API_KEY", raising=False)
    monkeypatch.setattr(
        rates,
        "fetch_public_chart_us2y_reaction",
        lambda spec, event, now: {
            "status": "READY",
            "provider": "trading_economics_public_chart",
            "quality": "PUBLIC_WEB_CHART_5M_SHADOW",
            "trade_execution": False,
        },
    )
    cfg = {
        "intraday_us2y": {
            "enabled": True,
            "min_event_age_minutes": 5,
            "max_event_age_minutes": 120,
            "public_chart_fallback": {"enabled": True},
        }
    }
    out = rates.fetch_intraday_us2y_reaction(
        cfg,
        event_at=datetime(2026, 10, 14, 12, 30, tzinfo=UTC),
        as_of=datetime(2026, 10, 14, 12, 45, tzinfo=UTC),
    )
    assert out["status"] == "READY"
    assert out["provider"] == "trading_economics_public_chart"
    assert out["primary_provider_status"] == "UNCONFIGURED_CREDENTIAL"
    assert out["fallback_used"] is True


def test_public_fallback_stays_shadow_quality_in_config():
    cfg_path = Path(__file__).parents[1] / "config" / "macro-event-features-v1.json"
    cfg = json.loads(cfg_path.read_text())
    public = cfg["intraday_us2y"]["public_chart_fallback"]
    assert cfg["version"] == "macro-event-feature-v1.12.0"
    assert public["enabled"] is True
    assert public["interval"] == "5m"
    assert public["quality"] == "PUBLIC_WEB_CHART_5M_SHADOW"
