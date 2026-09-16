from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.macro_event.collect_tradingeconomics import (
    canonical_event_type,
    normalize_records,
)


def test_official_nfp_example_normalizes_consensus_and_utc():
    rows = [
        {
            "CalendarId": "87220",
            "Date": "2016-12-02T13:30:00",
            "Country": "United States",
            "Category": "Non Farm Payrolls",
            "Event": "Non Farm Payrolls",
            "Actual": "178K",
            "Previous": "142K",
            "Forecast": "175K",
            "TEForecast": "180K",
            "Revised": "161K",
            "Unit": "K",
            "DateSpan": "0",
            "Importance": 3,
        }
    ]
    out = normalize_records(rows)
    row = out.iloc[0]
    assert row["event_type"] == "NFP"
    assert row["actual"] == 178000
    assert row["consensus"] == 175000
    # Revised is the pre-revision value; Previous is the revised prior.
    assert row["previous"] == 161000
    assert row["revised_previous"] == 142000
    assert str(row["release_time"].tz) == "UTC"


def test_initial_claims_numeric_values_take_priority():
    rows = [
        {
            "CalendarId": "313272",
            "Date": "2023-04-27T12:30:00",
            "Country": "United States",
            "Category": "Initial Jobless Claims",
            "Event": "Initial Jobless Claims",
            "Actual": "230K",
            "ActualValue": 230000,
            "Previous": "246K",
            "PreviousValue": 246000,
            "Forecast": "248K",
            "ForecastValue": 248000,
            "Revised": "245K",
            "DateSpan": "0",
        }
    ]
    out = normalize_records(rows)
    row = out.iloc[0]
    assert row["event_type"] == "INITIAL_CLAIMS"
    assert row["actual"] == 230000
    assert row["consensus"] == 248000
    assert row["previous"] == 245000
    assert row["revised_previous"] == 246000


def test_close_named_variants_are_not_silently_mapped():
    assert canonical_event_type(
        {"Event": "Retail Sales Ex Autos MoM", "Category": "Retail Sales"}
    ) is None
    assert canonical_event_type(
        {"Event": "ADP Employment Change", "Category": "Employment Change"}
    ) is None
    assert canonical_event_type(
        {"Event": "U-6 Unemployment Rate", "Category": "Unemployment Rate"}
    ) is None


def test_core_cpi_precedes_headline_rule():
    assert canonical_event_type(
        {"Event": "Core Inflation Rate MoM", "Category": "Core Inflation Rate"}
    ) == "CORE_CPI_MOM"
    assert canonical_event_type(
        {"Event": "Inflation Rate MoM", "Category": "Inflation Rate"}
    ) == "CPI_MOM"


def test_estimated_timestamp_is_excluded_by_default():
    rows = [
        {
            "CalendarId": "x",
            "Date": "2024-01-01T13:30:00",
            "Country": "United States",
            "Category": "Unemployment Rate",
            "Event": "Unemployment Rate",
            "Actual": "4.0%",
            "Forecast": "3.9%",
            "DateSpan": "1",
        }
    ]
    assert normalize_records(rows).empty
    assert len(normalize_records(rows, allow_estimated_time=True)) == 1
