from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from engine.r5_shadow_ledger import Snapshot, build_trades


def snap(
    hour: int,
    symbol: str,
    entry: bool,
    selected_price: str,
    *,
    extra: dict[str, str] | None = None,
) -> Snapshot:
    prices = {symbol: Decimal(selected_price)}
    for k, v in (extra or {}).items():
        prices[k] = Decimal(v)
    return Snapshot(
        run_id=f"run-{hour}-{symbol}",
        as_of=datetime(2026, 9, 10, hour, 30, tzinfo=timezone.utc),
        symbol=symbol,
        entry_signal=entry,
        selected_price=Decimal(selected_price),
        prices=prices,
    )


class R5ShadowLedgerTests(unittest.TestCase):
    def test_entry_exit_reentry_and_open_trade(self) -> None:
        snapshots = [
            snap(13, "AAPL", False, "315.57"),
            snap(14, "MU", True, "984.18"),
            snap(15, "ORCL", False, "156.18", extra={"MU": "977.31"}),
            snap(16, "QCOM", True, "178.53"),
            snap(17, "INTC", False, "103.80", extra={"QCOM": "182.60"}),
            snap(18, "INTC", True, "103.34"),
            snap(19, "ADBE", False, "254.16", extra={"INTC": "103.55"}),
            snap(20, "ORCL", True, "143.575"),
        ]

        trades = build_trades(snapshots)

        self.assertEqual([t.symbol for t in trades], ["MU", "QCOM", "INTC", "ORCL"])
        self.assertEqual(sum(t.exit_time is not None for t in trades), 3)
        self.assertIsNone(trades[-1].exit_time)

        self.assertAlmostEqual(trades[0].return_pct or 0.0, 977.31 / 984.18 - 1, places=12)
        self.assertAlmostEqual(trades[1].return_pct or 0.0, 182.60 / 178.53 - 1, places=12)
        self.assertAlmostEqual(trades[2].return_pct or 0.0, 103.55 / 103.34 - 1, places=12)

    def test_same_symbol_true_signal_is_hold_not_reentry(self) -> None:
        snapshots = [
            snap(14, "ORCL", True, "143.00"),
            snap(15, "ORCL", True, "144.00"),
            snap(16, "ORCL", True, "145.00"),
        ]
        trades = build_trades(snapshots)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].symbol, "ORCL")
        self.assertEqual(trades[0].entry_price, Decimal("143.00"))
        self.assertIsNone(trades[0].exit_time)

    def test_same_symbol_gate_off_exits(self) -> None:
        snapshots = [
            snap(14, "ORCL", True, "143.00"),
            snap(15, "ORCL", False, "142.00"),
        ]
        trades = build_trades(snapshots)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].exit_reason, "ENTRY_GATE_OFF")
        self.assertEqual(trades[0].exit_price, Decimal("142.00"))

    def test_selector_change_exits_even_if_next_entry_false(self) -> None:
        snapshots = [
            snap(14, "MU", True, "100.00"),
            snap(15, "ORCL", False, "150.00", extra={"MU": "101.00"}),
        ]
        trades = build_trades(snapshots)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].symbol, "MU")
        self.assertEqual(trades[0].exit_reason, "SELECTOR_CHANGED")
        self.assertEqual(trades[0].exit_price, Decimal("101.00"))


if __name__ == "__main__":
    unittest.main()
