from __future__ import annotations

import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.execution_cost_calibrator import calibrate


def _make_db(path, pairs: int):
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TABLE managed_position (
            position_id TEXT, created_at TEXT,
            entry_client_order_id TEXT, entry_avg_fill_price TEXT,
            exit_client_order_id TEXT, exit_avg_fill_price TEXT
        )''')
        conn.execute('''CREATE TABLE order_guard (
            client_order_id TEXT, symbol TEXT, side TEXT, status TEXT,
            created_at TEXT, telemetry_json TEXT
        )''')
        for i in range(pairs):
            entry=f'e{i}'
            exit_=f'x{i}'
            conn.execute(
                'INSERT INTO managed_position VALUES (?,?,?,?,?,?)',
                (f'p{i}','2026-01-01T00:00:00Z',entry,'100.02',exit_,'100.98'),
            )
            buy_t={
                'pretrade_quote': {'best_ask':'100.00','best_bid':'99.98','spread_bps':2.0},
                'broker_order': {'average_filled_price':'100.02','filled_quantity':'1','commission':'0.01','tax':'0','broker_fill_latency_ms':100},
            }
            sell_t={
                'pretrade_quote': {'best_bid':'101.00','best_ask':'101.02','spread_bps':1.98},
                'broker_order': {'average_filled_price':'100.98','filled_quantity':'1','commission':'0.01','tax':'0.01','broker_fill_latency_ms':120},
            }
            conn.execute('INSERT INTO order_guard VALUES (?,?,?,?,?,?)',(entry,'AAA','BUY','FILLED','2026-01-01T00:00:00Z',json.dumps(buy_t)))
            conn.execute('INSERT INTO order_guard VALUES (?,?,?,?,?,?)',(exit_,'AAA','SELL','FILLED','2026-01-01T01:00:00Z',json.dumps(sell_t)))
        conn.commit()


def test_calibrator_blocks_small_sample(tmp_path):
    db=tmp_path/'trading.sqlite3'
    _make_db(db, 3)
    got=calibrate(db)
    assert got['sample_gate']['sufficient'] is False
    assert got['promotion_gate']=='BLOCK_INSUFFICIENT_EXECUTION_SAMPLE'
    assert got['recommended_backtest_round_trip_bps']==20.0


def test_calibrator_uses_empirical_distribution_after_threshold(tmp_path):
    db=tmp_path/'trading.sqlite3'
    _make_db(db, 15)
    got=calibrate(db)
    assert got['sample_gate']['sufficient'] is True
    assert got['slippage_bps']['buy']['n']==15
    assert got['slippage_bps']['sell']['n']==15
    assert got['promotion_gate']=='READY_EMPIRICAL_COST'
    assert got['recommended_backtest_round_trip_bps'] >= 20.0
