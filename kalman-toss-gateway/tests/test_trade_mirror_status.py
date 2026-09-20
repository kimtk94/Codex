from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.trade_mirror import _execution_status


def test_entry_prefers_reconciled_managed_position_status():
    status, source = _execution_status(
        {"status": "SUBMITTED"},
        {"entry_status": "FILLED"},
        "ENTRY",
    )
    assert status == "FILLED"
    assert source == "managed_position"


def test_exit_prefers_reconciled_managed_position_status():
    status, source = _execution_status(
        {"status": "SUBMITTED"},
        {"exit_status": "CANCELED"},
        "EXIT",
    )
    assert status == "CANCELED"
    assert source == "managed_position"


def test_unmatched_order_falls_back_to_order_guard_status():
    status, source = _execution_status(
        {"status": "AMBIGUOUS"},
        None,
        None,
    )
    assert status == "AMBIGUOUS"
    assert source == "order_guard"


def test_missing_reconciled_status_falls_back_to_order_guard_status():
    status, source = _execution_status(
        {"status": "SUBMITTED"},
        {"entry_status": None},
        "ENTRY",
    )
    assert status == "SUBMITTED"
    assert source == "order_guard"
