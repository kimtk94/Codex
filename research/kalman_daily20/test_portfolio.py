"""Synthetic, offline portfolio accounting and OOS governance contracts."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from daily20 import load_spec, market_file
from portfolio import (
    INITIAL_CASH, buy_hold, build_report, classify_state, market_state,
    performance, prepared_events, simulate
)


def mock_prices(sessions, symbols=("AAA", "BBB", "SPY", "QQQ", "^VIX")):
    table = {}
    for symbol in symbols:
        level = 18.0 if symbol == "^VIX" else 100.0
        table[symbol] = pd.DataFrame(
            {"open": level, "close": level},
            index=pd.DatetimeIndex(sessions),
        )
    return table


def event(symbol, sessions, *, signal_i, entry_i, exit_i, score=0.8):
    return {
        "symbol": symbol, "strategy": "LOGISTIC",
        "signal_date": sessions[signal_i], "entry_date": sessions[entry_i],
        "exit_date": sessions[exit_i], "priority": score,
        "signal_regime": "BULL", "signal_volatility": "VIX_LT20",
        "signal_tech_leadership": "TECH_LEADS",
    }


class LedgerContracts(unittest.TestCase):
    def test_open_cash_competition_and_no_same_close_reuse(self):
        days = pd.bdate_range("2024-01-02", periods=10)
        prices = mock_prices(days)
        signals = [
            event("AAA", days, signal_i=0, entry_i=1, exit_i=3, score=0.6),
            event("BBB", days, signal_i=0, entry_i=1, exit_i=3, score=0.9),
            event("AAA", days, signal_i=2, entry_i=3, exit_i=6, score=0.9),
            event("AAA", days, signal_i=3, entry_i=4, exit_i=7, score=0.8),
        ]
        curve, filled, skipped = simulate(
            signals, prices, days, strategy="LOGISTIC", cohort="ALL_20",
            max_positions=1, allocation=1.0, round_trip_cost_bps=20,
        )
        self.assertEqual(filled.symbol.tolist(), ["BBB", "AAA"])
        self.assertEqual(filled["entry_date"].tolist(), [
            str(days[1].date()), str(days[4].date())
        ])
        self.assertEqual(filled["exit_date"].tolist(), [
            str(days[3].date()), str(days[7].date())
        ])
        self.assertEqual(skipped["max_positions"], 2)
        self.assertTrue((curve["cash"] >= -1e-8).all())
        self.assertTrue((curve["gross_exposure"] <= 1.0000001).all())
        self.assertLess(curve["equity"].iloc[-1], INITIAL_CASH)
        self.assertEqual(int(curve["active_positions"].iloc[-1]), 0)

    def test_stricter_costs_always_reduce_identical_trade_realized_return(self):
        days = pd.bdate_range("2024-01-02", periods=7)
        prices = mock_prices(days)
        signals = [event("AAA", days, signal_i=0, entry_i=1, exit_i=4)]
        _, cheap, _ = simulate(signals, prices, days, strategy="LOGISTIC",
                               cohort="ALL_20", max_positions=1, allocation=1.0,
                               round_trip_cost_bps=20)
        _, costly, _ = simulate(signals, prices, days, strategy="LOGISTIC",
                                cohort="ALL_20", max_positions=1, allocation=1.0,
                                round_trip_cost_bps=40)
        self.assertLess(float(costly["realized_return"].iloc[0]),
                        float(cheap["realized_return"].iloc[0]))

    def test_mark_to_market_drawdown_without_changing_trade_outcome(self):
        days = pd.bdate_range("2024-01-02", periods=6)
        prices = mock_prices(days)
        prices["AAA"].loc[days[2], "close"] = 60
        prices["AAA"].loc[days[3], "close"] = 100
        signals = [event("AAA", days, signal_i=0, entry_i=1, exit_i=4)]
        curve, _, _ = simulate(signals, prices, days, strategy="LOGISTIC",
                               cohort="ALL_20", max_positions=1, allocation=1.0,
                               round_trip_cost_bps=0)
        metrics = performance(curve)
        self.assertLess(metrics["max_close_drawdown"], -0.39)
        self.assertEqual(round(metrics["total_return"], 12), 0)

    def test_benchmark_common_performance_schema(self):
        days = pd.bdate_range("2024-01-02", periods=10)
        prices = mock_prices(days)
        prices["SPY"]["close"] = np.arange(10) + 100.0
        metrics = buy_hold(prices, days, "SPY")
        self.assertAlmostEqual(metrics["total_return"], 9 / 100)
        self.assertAlmostEqual(metrics["active_session_pct"], 1.0)
        self.assertAlmostEqual(metrics["average_gross_exposure"], 1.0)

    def test_lagged_regime_uses_previous_session_not_today(self):
        days = pd.bdate_range("2023-01-02", periods=230)
        prices = mock_prices(days)
        prices["SPY"]["close"] = np.arange(230, dtype=float) + 100
        prices["QQQ"]["close"] = np.arange(230, dtype=float) + 200
        prices["^VIX"]["close"] = 18.0
        state = market_state(prices)
        self.assertEqual(classify_state(state.loc[days[-1]])[0], "BULL")
        self.assertEqual(classify_state(state.loc[days[-1]])[1], "VIX_LT20")
        prices["^VIX"].loc[days[-1], "close"] = 99.0
        future = market_state(prices)
        self.assertEqual(classify_state(future.loc[days[-1]])[1], "VIX_LT20")

    def test_outdated_trade_label_fails_closed(self):
        days = pd.bdate_range("2023-01-02", periods=300)
        prices = mock_prices(days)
        prices["SPY"]["close"] = np.arange(300) + 100.0
        prices["QQQ"]["close"] = np.arange(300) + 100.0
        state = market_state(prices)
        signal_i, entry_i, exit_i = 270, 271, 274
        row = {
            "symbol": "SPY", "strategy": "LOGISTIC",
            "signal_date": str(days[signal_i].date()),
            "entry_date": str(days[entry_i].date()),
            "exit_date": str(days[exit_i].date()),
            "gross_return": 1.0, "net_return": 0.998,
            "probability": .8, "regime": "BULL",
        }
        with self.assertRaisesRegex(RuntimeError, "STALE_OOS_TRADE"):
            prepared_events(pd.DataFrame([row]), prices, state,
                            strategy="LOGISTIC", excluded=set())


class EndToEndContracts(unittest.TestCase):
    def test_all_sixteen_scenarios_from_synthetic_adjusted_bars(self):
        spec = load_spec()
        days = pd.bdate_range("2023-01-02", periods=790)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "market"
            close_map = {}
            for n, symbol in enumerate(set(spec["core"]) | {"^VIX"}):
                close = np.full(len(days), 18.0) if symbol == "^VIX" else (
                    100.0 + n + np.arange(len(days)) * .04)
                close_map[symbol] = close
                frame = pd.DataFrame({
                    "timestamp": days, "open": close - .02,
                    "high": close + .1, "low": close - .1, "close": close,
                    "volume": 10000,
                })
                path = market_file(data, symbol)
                path.parent.mkdir(parents=True, exist_ok=True)
                frame.to_parquet(path, index=False)
            rows = []
            for symbol in spec["core"]:
                for session in (350, 390, 520, 560):
                    entry, exit_at = session + 1, session + 4
                    close = close_map[symbol]
                    gross = close[exit_at] / (close[entry] - .02) - 1
                    for strategy in ("LOGISTIC", "TREND_RULE"):
                        rows.append({
                            "symbol": symbol, "strategy": strategy,
                            "signal_date": str(days[session].date()),
                            "entry_date": str(days[entry].date()),
                            "exit_date": str(days[exit_at].date()),
                            "gross_return": gross,
                            "net_return": gross - .002,
                            "probability": .7 if strategy == "LOGISTIC" else np.nan,
                            "regime": "BULL",
                        })
            trades_path = root / "trades.csv"
            pd.DataFrame(rows).to_csv(trades_path, index=False)
            result = build_report(spec, data, trades_path, root / "results")
            self.assertEqual(result["scenario_count"], 16)
            self.assertEqual(len(result["primary_scenarios"]), 4)
            self.assertEqual(len(result["benchmark"]), 2)
            self.assertTrue(all(x["executed_trades"] > 0
                                for x in result["primary_scenarios"]))
            self.assertTrue((root / "results/portfolio_annual.csv").exists())
            self.assertTrue((root / "results/portfolio_daily_equity.csv").exists())
            self.assertFalse(result["tradable_strategy_approved"])
            self.assertTrue(result["portfolio_mdd_available"])
            for name in result["regime_attribution"]:
                by_trend = result["regime_attribution"][name]["trades_at_entry"]["signal_regime"]
                self.assertEqual(set(by_trend), {"BULL"})


if __name__ == "__main__":
    unittest.main()
