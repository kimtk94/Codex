from datetime import date

import numpy as np
import pandas as pd

import research.macro_event.collect_fred_alfred as fred


def test_release_timestamp_respects_new_york_dst():
    jan = fred._release_ts_utc("2026-01-15", "08:30")
    jul = fred._release_ts_utc("2026-07-15", "08:30")
    assert str(jan) == "2026-01-15 13:30:00+00:00"
    assert str(jul) == "2026-07-15 12:30:00+00:00"


def test_collect_events_uses_initial_release_vintage(monkeypatch):
    def fake_initial_release_rows(*args, **kwargs):
        return [
            {
                "realtime_start": "2026-09-11",
                "realtime_end": "2026-10-01",
                "date": "2026-08-01",
                "value": "323.976",
            }
        ]

    monkeypatch.setattr(fred, "_initial_release_rows", fake_initial_release_rows)
    monkeypatch.setattr(
        fred,
        "EVENT_SERIES",
        {
            "CPI_MOM": {
                "series_id": "CPIAUCSL",
                "release_time_et": "08:30",
                "transform": "pct_change",
            }
        },
    )
    out = fred.collect_events(
        api_key="x" * 32,
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        timeout_seconds=1.0,
        max_retries=1,
    )
    row = out.iloc[0]
    assert row["event_id"] == "FRED:CPIAUCSL:2026-08-01:2026-09-11"
    assert row["actual"] == 323.976
    assert pd.isna(row["consensus"])
    assert row["signal_basis"] == "INITIAL_RELEASE_CHANGE_PROXY"
    assert str(row["available_time"]) == "2026-09-11 12:30:00+00:00"


def test_daily_2y_enrichment_uses_same_release_date_only():
    events = pd.DataFrame(
        {
            "available_time": pd.to_datetime(
                ["2026-09-11 12:30Z", "2026-09-12 12:30Z"]
            )
        }
    )
    rates = pd.DataFrame(
        {
            "date": ["2026-09-10", "2026-09-11"],
            "us_treasury_2y": [3.50, 3.57],
        }
    )
    out = fred.enrich_events_with_daily_2y(events, rates)
    assert np.isclose(out.loc[0, "us2y_daily_bp"], 7.0)
    assert pd.isna(out.loc[1, "us2y_daily_bp"])


def test_secret_redaction():
    secret = "a" * 32
    text = fred._redact(f"failed?api_key={secret}", secret)
    assert secret not in text
    assert "<REDACTED>" in text
