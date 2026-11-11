"""Contract tests for guarded LIVE policy patch and read-only observer."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]/"scripts"

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

apply=load("apply_flip_fast_2026","apply_profit_flip_minus2_fast_check.py")
fast=load("fast_flip_check_2026","fast_profit_flip_check.py")

CONFIG=(
"AUTO_TRADE_PROFIT_FLIP_GUARD_ENABLED=true\n"
"AUTO_TRADE_PROFIT_FLIP_ARM_PCT=0.002\n"
"AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT=-0.002\n"
"AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS=2\n"
"AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT=0\n"
"AUTO_TRADE_STOP_LOSS_PCT=-0.03\n"
"AUTO_TRADE_FRIDAY_FLAT_ENABLED=true\n"
)

class PolicyPatchTests(unittest.TestCase):
    def test_only_trigger_changed(self):
        got=apply.update_env(CONFIG)
        self.assertEqual(got.replace("TRIGGER_PCT=-0.02","TRIGGER_PCT=-0.002"), CONFIG)

    def test_idempotent(self):
        first=apply.update_env(CONFIG)
        self.assertEqual(first,apply.update_env(first))

    def test_guard_disabled_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"GUARD_ENABLED"):
            apply.update_env(CONFIG.replace("GUARD_ENABLED=true","GUARD_ENABLED=false"))

    def test_legacy_stop_changed_refused(self):
        with self.assertRaisesRegex(ValueError,"STOP_LOSS_PCT"):
            apply.update_env(CONFIG.replace("STOP_LOSS_PCT=-0.03","STOP_LOSS_PCT=-0.04"))

    def test_unexpected_trigger_refused(self):
        with self.assertRaisesRegex(ValueError,"Unexpected"):
            apply.update_env(CONFIG.replace("TRIGGER_PCT=-0.002","TRIGGER_PCT=-0.01"))

    def test_cron_keeps_live_execution_5m(self):
        base="CRON_TZ=Asia/Seoul\n*/5 * * * * root /opt/kalman/app/scripts/run_us_market_clock.sh execution\n*/30 9-21 * * 1-5 root /opt/kalman/app/scripts/run_position_watch.sh\n"
        x=apply.update_cron(base)
        self.assertEqual(x.count(apply.MARKER),1)
        self.assertIn("*/5 * * * * root /opt/kalman/app/scripts/run_us_market_clock.sh execution",x)
        self.assertIn("*/30 9-21",x)
        self.assertEqual(x.count("fast_profit_flip_check.py"),2)
        self.assertEqual(x,apply.update_cron(x))

    def test_pending_flip_blocker(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"trading.sqlite3"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE managed_position(state TEXT, exit_pending_reason TEXT)")
                conn.execute("INSERT INTO managed_position VALUES ('OPEN','PROFIT_TO_LOSS_FLIP')")
            with self.assertRaisesRegex(RuntimeError,"pending"):
                apply.assert_no_old_pending(CONFIG+"TRADING_STATE_DB="+str(db)+"\n")
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE managed_position SET exit_pending_reason=NULL")
            apply.assert_no_old_pending(CONFIG+"TRADING_STATE_DB="+str(db)+"\n")

    def test_readonly_sql_query(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"trading.sqlite3"
            with sqlite3.connect(db) as conn:
                conn.execute("""CREATE TABLE managed_position(position_id TEXT,symbol TEXT,state TEXT,
                    entry_avg_fill_price TEXT,peak_price_return TEXT,profit_flip_armed INTEGER,
                    profit_flip_negative_count INTEGER,exit_pending_reason TEXT,
                    entry_count INTEGER,created_at TEXT)""")
                conn.execute("INSERT INTO managed_position VALUES ('p1','AMD','OPEN','100','0.003',1,0,NULL,1,'today')")
            rows=fast.get_active_positions(db)
            self.assertEqual([x["symbol"] for x in rows],["AMD"])
            self.assertEqual(len(rows),1)

if __name__=="__main__":
    unittest.main()
