import json
from pathlib import Path

import pandas as pd

from engine import macro_equity_confirmation_v1 as equity


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "t": pd.to_datetime(
                [
                    "2026-10-08T13:30:00Z",
                    "2026-10-08T14:30:00Z",
                    "2026-10-08T15:30:00Z",
                    "2026-10-08T16:30:00Z",
                    "2026-10-08T17:30:00Z",
                ],
                utc=True,
            ),
            "o": [100.0, 100.0, 98.0, 97.0, 96.0],
            "c": [101.0, 98.0, 97.0, 96.0, 95.0],
        }
    )


def test_symbol_reaction_never_uses_bar_before_event():
    bars = equity.load_hourly_bars_from_frame(_bars())
    out = equity.compute_symbol_reaction(
        bars,
        event_at=pd.Timestamp("2026-10-08T13:40:00Z"),
        surprise_score=1.0,
        horizons_bars=[1, 4],
        max_entry_lag_minutes=90,
    )
    assert out["status"] == "READY"
    assert out["entry_ts"] == "2026-10-08T14:30:00+00:00"
    assert out["entry_lag_minutes"] == 50.0
    assert abs(out["reactions"]["1bar"]["return"] - (-0.02)) < 1e-12
    assert out["reactions"]["1bar"]["direction_confirmed"] is True


def test_event_after_bar_start_advances_to_next_bar():
    bars = equity.load_hourly_bars_from_frame(_bars())
    out = equity.compute_symbol_reaction(
        bars,
        event_at=pd.Timestamp("2026-10-08T14:40:00Z"),
        surprise_score=1.0,
        horizons_bars=[1],
        max_entry_lag_minutes=90,
    )
    assert out["entry_ts"] == "2026-10-08T15:30:00+00:00"
    assert out["entry_lag_minutes"] == 50.0


def test_optional_missing_soxx_does_not_degrade(tmp_path: Path):
    qqq = tmp_path / "QQQ.parquet"
    _bars().to_parquet(qqq, index=False)
    cfg = {
        "equity_confirmation": {
            "enabled": True,
            "max_entry_lag_minutes": 90,
            "horizons_bars": [1, 4],
            "symbols": {
                "QQQ": {
                    "path": str(qqq),
                    "required": True,
                    "source": "TEST",
                },
                "SOXX": {
                    "path": str(tmp_path / "missing_soxx.parquet"),
                    "required": False,
                    "source": "TEST_OPTIONAL",
                },
            },
        }
    }
    out = equity.compute_equity_confirmation(
        cfg,
        event_at=pd.Timestamp("2026-10-08T13:40:00Z"),
        surprise_score=1.0,
    )
    assert out["status"] == "READY"
    assert out["required_failures"] == []
    assert out["symbols"]["QQQ"]["status"] == "READY"
    assert out["symbols"]["SOXX"]["status"] == "UNAVAILABLE_OPTIONAL"
    assert out["trade_execution"] is False


def test_missing_required_symbol_degrades(tmp_path: Path):
    cfg = {
        "equity_confirmation": {
            "enabled": True,
            "symbols": {
                "QQQ": {
                    "path": str(tmp_path / "missing.parquet"),
                    "required": True,
                }
            },
        }
    }
    out = equity.compute_equity_confirmation(
        cfg,
        event_at=pd.Timestamp("2026-10-08T13:40:00Z"),
        surprise_score=-1.0,
    )
    assert out["status"] == "DEGRADED_REQUIRED_DATA"
    assert out["required_failures"] == ["QQQ"]


def test_module_has_no_execution_side_effects():
    source = Path(equity.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "trade_execution = True"):
        assert forbidden not in source


def test_production_config_keeps_pce_and_equity_shadow_only():
    cfg_path = Path(__file__).parents[1] / "config" / "macro-event-features-v1.json"
    cfg = json.loads(cfg_path.read_text())
    assert cfg["version"] == "macro-event-feature-v1.12.0"
    assert cfg["event_scoring"]["indicator_family"]["CORE_PCE_MOM"] == "PCE"
    assert cfg["event_scoring"]["indicator_family"]["CORE_PCE_YOY"] == "PCE"
    assert cfg["event_scoring"]["weights"]["PCE"] == {
        "surprise": 0.5,
        "us2y": 0.3,
        "policy": 0.2,
    }
    assert cfg["equity_confirmation"]["shadow_only"] is True
    assert cfg["equity_confirmation"]["symbols"]["QQQ"]["required"] is True
    assert cfg["equity_confirmation"]["symbols"]["SOXX"]["required"] is False


def test_production_config_intraday_us2y_is_shadow_only():
    cfg_path = Path(__file__).parents[1] / "config" / "macro-event-features-v1.json"
    cfg = json.loads(cfg_path.read_text())
    intraday = cfg["intraday_us2y"]
    assert intraday["enabled"] is True
    assert intraday["symbol"] == "USGG2YR:IND"
    assert intraday["interval"] == "1m"
    assert intraday["confirmation_horizon"] == "15m"
    assert intraday["shadow_only"] is True
    assert intraday["quality"] == "DELAYED_INTRADAY_RESEARCH"


def test_production_config_public_us2y_fallback_is_shadow_only():
    cfg_path = Path(__file__).parents[1] / "config" / "macro-event-features-v1.json"
    cfg = json.loads(cfg_path.read_text())
    public = cfg["intraday_us2y"]["public_chart_fallback"]
    assert public["enabled"] is True
    assert public["interval"] == "5m"
    assert public["quality"] == "PUBLIC_WEB_CHART_5M_SHADOW"
