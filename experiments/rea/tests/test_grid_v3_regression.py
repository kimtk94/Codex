#!/usr/bin/env python3
"""Offline, deterministic regression tests for the untouched Grid V3 research engine."""
import importlib.util
import sqlite3
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "research/upbit_eth/grid_event_v3.py"
spec = importlib.util.spec_from_file_location("grid_event_v3", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def run(bars, *, space=.01, n=20, fee=.001, capital=1_000_000):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE candles(ts_utc TEXT, high REAL, low REAL, close REAL)")
    con.executemany("INSERT INTO candles VALUES (?,?,?,?)", bars)
    result = mod.sim(con, 2025, space, n, capital, fee)
    con.close()
    return result

def bar(minute, h=2_000_000, l=2_000_000, c=2_000_000):
    return (f"2025-01-01T00:{minute:02}:00+00:00", h, l, c)

class GridRegression(unittest.TestCase):
    def test_no_fills_flat_price(self):
        r=run([bar(0),bar(1)])
        self.assertEqual(r["fills"],0)
        self.assertEqual(r["gap_resets"],0)
        self.assertAlmostEqual(r["return_pct"],0,places=4)

    def test_strict_touch_equality_is_not_fill(self):
        # First bid: floor(2m/1.01 to 500-KRW tick) = 1,980,000
        bid=1_980_000
        r=run([bar(0),bar(1,h=2_000_000,l=bid,c=2_000_000)])
        self.assertEqual(r["fills"],0)

    def test_buy_crossing_executes(self):
        r=run([bar(0),bar(1,h=2_000_000,l=1_979_500,c=2_000_000)])
        self.assertGreaterEqual(r["fills"],1)
        self.assertGreater(r["fees_krw"],0)

    def test_both_sides_touched_is_ambiguous(self):
        r=run([bar(0),bar(1,h=2_030_000,l=1_970_000,c=2_000_000)])
        self.assertEqual(r["fills"],0)
        self.assertEqual(r["ambiguous_bars"],1)

    def test_gap_resets_without_fill_in_gap_candle(self):
        r=run([bar(0),bar(8,h=3_000_000,l=1_000_000,c=2_000_000)])
        self.assertEqual(r["gap_resets"],1)
        self.assertEqual(r["fills"],0)

    def test_missing_year_returns_none(self):
        self.assertIsNone(run([("2024-01-01T00:00:00+00:00",2e6,2e6,2e6)]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
