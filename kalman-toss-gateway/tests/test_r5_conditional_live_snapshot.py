from datetime import datetime, timezone

from engine.r5_conditional_live import _snapshot_rank_context


def _signal(symbol="ORCL", as_of="2026-10-02T17:30:00+00:00"):
    return {
        "symbol": symbol,
        "as_of": datetime.fromisoformat(as_of),
    }


def test_snapshot_rank_context_extracts_matching_top2():
    snapshot = {
        "data_as_of": "2026-10-02T17:30:00.000Z",
        "payload": {
            "top3": [
                {"rank": 1, "symbol": "ORCL", "model_score": 0.0006136439258906945},
                {"rank": 2, "symbol": "MDT", "model_score": 0.0003425057411946199},
                {"rank": 3, "symbol": "DE", "model_score": 0.0003263792599284554},
            ]
        },
    }
    r1, r2_symbol, r2 = _snapshot_rank_context(snapshot, _signal())
    assert r1 == 0.0006136439258906945
    assert r2_symbol == "MDT"
    assert r2 == 0.0003425057411946199


def test_snapshot_rank_context_rejects_stale_timestamp():
    snapshot = {
        "data_as_of": "2026-10-01T17:30:00.000Z",
        "payload": {
            "top3": [
                {"rank": 1, "symbol": "ORCL", "model_score": 0.1},
                {"rank": 2, "symbol": "MDT", "model_score": 0.09},
            ]
        },
    }
    assert _snapshot_rank_context(snapshot, _signal()) == (None, None, None)


def test_snapshot_rank_context_rejects_rank1_symbol_mismatch():
    snapshot = {
        "data_as_of": "2026-10-02T17:30:00.000Z",
        "payload": {
            "top3": [
                {"rank": 1, "symbol": "MDT", "model_score": 0.1},
                {"rank": 2, "symbol": "ORCL", "model_score": 0.09},
            ]
        },
    }
    assert _snapshot_rank_context(snapshot, _signal()) == (None, None, None)


def test_native_web_snapshot_schema_extracts_rank_context():
    snapshot = {
        "model_as_of_utc": "2026-10-02T18:30:00+00:00",
        "today_selector": {
            "selected_symbol": "BA",
            "model_score": 0.0006136439258906945,
            "as_of_utc": "2026-10-02 18:30:00+00:00",
        },
        "model_universe": {
            "BA": {"model_score": 0.0006136439258906945},
            "DE": {"model_score": 0.0005314615217972279},
            "TSLA": {"model_score": 0.0005314615217972279},
            "ORCL": {"model_score": 0.00046954792904392627},
        },
    }
    signal = {
        "symbol": "BA",
        "as_of": datetime.fromisoformat("2026-10-02T18:30:00+00:00"),
    }
    r1, r2_symbol, r2 = _snapshot_rank_context(snapshot, signal)
    assert r1 == 0.0006136439258906945
    assert r2_symbol == "DE"
    assert r2 == 0.0005314615217972279


def test_native_web_snapshot_rejects_selected_symbol_mismatch():
    snapshot = {
        "model_as_of_utc": "2026-10-02T18:30:00+00:00",
        "today_selector": {
            "selected_symbol": "ORCL",
            "model_score": 0.0006136439258906945,
        },
        "model_universe": {
            "BA": {"model_score": 0.0006136439258906945},
            "DE": {"model_score": 0.0005314615217972279},
        },
    }
    signal = {
        "symbol": "BA",
        "as_of": datetime.fromisoformat("2026-10-02T18:30:00+00:00"),
    }
    assert _snapshot_rank_context(snapshot, signal) == (None, None, None)
