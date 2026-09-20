from __future__ import annotations

from engine.r5_strategy_ledger_sync import _build_forward_record


def test_build_closed_forward_record_matches_canonical_cost_semantics():
    trade = {
        "trade_id": "R5P_HGB_REFIT_R4|9217",
        "selected_symbol": "ISRG",
        "expected_seq": 9217,
        "expected_exit_seq": 9221,
        "position_weight": 0.7087505796086545,
        "score": 0.0003310818521180993,
        "model_freeze_sha256": "freeze",
    }
    outcome = {
        "gross_return": -0.008830497440396561,
        "net10_return": -0.009539248020005215,
    }
    prices = {
        ("ISRG", 9217): ("2026-09-16T14:30:00+00:00", 386.46),
        ("ISRG", 9221): ("2026-09-16T18:30:00+00:00", 381.645),
    }

    record = _build_forward_record(
        trade, outcome, lambda symbol, seq: prices.get((symbol, seq), (None, None))
    )

    assert record["entry_price"] == 386.46
    assert record["exit_price"] == 381.645
    assert record["return_pct"] == outcome["net10_return"]
    assert record["exit_reason"] == "EXPECTED_SEQ_PLUS_4"
    meta = record["metadata"]
    assert meta["provenance"] == "R5_1_CANONICAL_FORWARD_LOG"
    assert meta["prospective"] is True
    assert meta["trade_execution"] is False
    assert meta["status"] == "CLOSED"
    assert abs(meta["raw_return"] - (-0.012459245458779633)) < 1e-12
    assert meta["gross_weighted_return"] == outcome["gross_return"]


def test_build_open_forward_record_stays_open():
    trade = {
        "trade_id": "R5P_HGB_REFIT_R4|9221",
        "selected_symbol": "GS",
        "expected_seq": 9221,
        "expected_exit_seq": 9225,
        "position_weight": 0.6260572204939656,
        "score": 0.00026716943548069414,
        "model_freeze_sha256": "freeze",
    }
    prices = {
        ("GS", 9221): ("2026-09-16T18:30:00+00:00", 935.44),
    }

    record = _build_forward_record(
        trade, None, lambda symbol, seq: prices.get((symbol, seq), (None, None))
    )

    assert record["entry_price"] == 935.44
    assert record["exit_time"] is None
    assert record["return_pct"] is None
    assert record["metadata"]["status"] == "OPEN"
    assert record["metadata"]["net10_return"] is None
