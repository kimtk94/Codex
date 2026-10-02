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
