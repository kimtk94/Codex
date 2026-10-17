from pathlib import Path
import sqlite3

import pandas as pd

from research.quant_stack import prediction_market_us_oos_ledger_v0 as ledger


def _spec():
    return {
        "hypothesis_id": "PMOOS-INFLATION-UP-QQQ-7B-V1",
        "discovery": {"data_end_utc": "2026-09-13T11:50:00Z"},
        "hypothesis": {
            "shock_threshold": 0.15,
            "dominant_channel": "INFLATION_UPSIDE",
            "horizon_bars": 7,
            "max_entry_lag_minutes": 90,
            "symbol": "QQQ",
        },
    }


def _prediction():
    return pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-10-08T14:00:00Z"),
                "slug": "cpic-test-gt3pt0pct",
                "question": "CPI YoY in September",
                "theme": "INFLATION",
                "semantic_channel": "INFLATION_UPSIDE",
                "risk_prior_sign": -1,
                "poly_delta_1h": 0.20,
            }
        ]
    )


def _asset(forward_return):
    return pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-10-08T14:00:00Z"),
                "price": 100.0,
                "symbol": "QQQ",
                "fwd_return_1bar": -0.01,
                "fwd_return_4bar": -0.03,
                "fwd_return_7bar": forward_return,
            }
        ]
    )


def test_ledger_row_outcome_ready_and_signed_return():
    rows = ledger.build_ledger_rows(
        _prediction(),
        _asset(-0.05),
        _spec(),
    )
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["outcome_state"] == "OUTCOME_READY"
    assert abs(float(row["event_score"]) - (-0.20)) < 1e-12
    assert abs(float(row["forward_return"]) - (-0.05)) < 1e-12
    assert abs(float(row["signed_return"]) - 0.05) < 1e-12


def test_ledger_waits_for_forward_horizon():
    rows = ledger.build_ledger_rows(
        _prediction(),
        _asset(float("nan")),
        _spec(),
    )
    assert len(rows) == 1
    assert rows.iloc[0]["outcome_state"] == "WAITING_HORIZON"
    assert pd.isna(rows.iloc[0]["signed_return"])


def test_event_id_stable_with_same_hour():
    a = ledger.event_id(
        "PMOOS-INFLATION-UP-QQQ-7B-V1",
        pd.Timestamp("2026-10-08T14:00:00Z"),
        "INFLATION_UPSIDE",
    )
    b = ledger.event_id(
        "PMOOS-INFLATION-UP-QQQ-7B-V1",
        pd.Timestamp("2026-10-08T14:00:00Z"),
        "INFLATION_UPSIDE",
    )
    assert a == b
    assert len(a) == 24


def test_persist_is_upsert_not_duplicate(tmp_path: Path):
    rows = ledger.build_ledger_rows(
        _prediction(),
        _asset(float("nan")),
        _spec(),
    )
    db = tmp_path / "ledger.sqlite3"
    pq = tmp_path / "ledger.parquet"

    first = ledger.persist_ledger(rows, sqlite_path=db, parquet_path=pq)
    assert first["events_total"] == 1
    assert first["new_events_this_run"] == 1

    rows2 = ledger.build_ledger_rows(
        _prediction(),
        _asset(-0.05),
        _spec(),
    )
    second = ledger.persist_ledger(rows2, sqlite_path=db, parquet_path=pq)
    assert second["events_total"] == 1
    assert second["new_events_this_run"] == 0
    assert second["states"]["OUTCOME_READY"] == 1

    con = sqlite3.connect(db)
    try:
        count = con.execute("select count(*) from events").fetchone()[0]
        state = con.execute(
            "select outcome_state from events"
        ).fetchone()[0]
    finally:
        con.close()
    assert count == 1
    assert state == "OUTCOME_READY"


def test_source_has_no_execution_side_effects():
    source = Path(ledger.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "trade_execution = True"):
        assert forbidden not in source
