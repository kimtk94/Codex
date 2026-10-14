"""Full shadow mirror integration against disposable local PostgreSQL + SQLite.

Requires opt-in KALMAN_AUDIT_E2E=1 and an EXACT hard-coded disposable DSN.
Never touches live, Neon, Toss, user files, or real credentials.
Creates 40 synthetic positions and 97 synthetic orders, runs the REAL
engine/trade_mirror.py process twice, checks PostgreSQL projection.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
GATEWAY = ROOT / "kalman-toss-gateway"
DSN = "postgresql://audit:audit@127.0.0.1:5432/kalman_audit"
UTC = "2026-10-14T12:00:00+00:00"
SCHEMA = Path(__file__).with_name("shadow_mirror_schema.sql")


def make_context(pid, symbol, run, kind, ordinal):
    return {"managed_position_id": pid, "symbol": symbol,
            "strategy_version": "AUDIT_SHADOW", "run_id": run,
            "entry_type": kind, "entry_count_before": ordinal,
            "signal_as_of": UTC,
            "execution_mode": "DRY_RUN", "signal_policy": "SHADOW_ONLY"}


def telemetry(oid, qty, px, *, fee_currency="USD", valid=True, context=None):
    b = {"order_id": oid, "status": "FILLED" if valid else "SUBMITTED",
         "currency": "USD", "filled_quantity": qty, "average_filled_price": px,
         "filled_amount": str(float(qty)*float(px)),
         "commission": "0.01", "tax": "0",
         "filled_at": UTC, "response_meta": {"status_code": 200}}
    if fee_currency is not None:
        # Only a SYNTHETIC explicit field; current Toss API schema does
        # not document this and source parser does not create it.
        b["fee_currency"] = fee_currency
    return json.dumps({"broker_order": b, "signal_context": context or {}},
                      separators=(",", ":"))


def build_sqlite(path):
    from engine.order_position_link import _expected_client_id
    db = sqlite3.connect(str(path))
    db.executescript("""
       CREATE TABLE managed_position(
          position_id TEXT, symbol TEXT, strategy_version TEXT, state TEXT,
          entry_run_id TEXT, entry_signal_as_of TEXT, entry_client_order_id TEXT,
          entry_order_id TEXT, entry_status TEXT, entry_filled_quantity TEXT,
          entry_avg_fill_price TEXT, remaining_quantity TEXT,
          entry_count INTEGER, target_exit_buckets INTEGER,
          exit_client_order_id TEXT, exit_order_id TEXT, exit_status TEXT,
          exit_avg_fill_price TEXT, exit_reason TEXT, note TEXT,
          exit_attempt INTEGER, created_at TEXT, updated_at TEXT
       );
       CREATE TABLE order_guard(
          client_order_id TEXT, created_at TEXT, trade_date_kst TEXT,
          symbol TEXT, side TEXT, estimated_notional_krw INTEGER,
          status TEXT, toss_order_id TEXT, error TEXT, telemetry_json TEXT
       );
    """)

    def position(pid, symbol, run, qty, entry_avg, exit_avg, *, entries=1):
        first = _expected_client_id(run, symbol)
        exit_id = "exit-" + pid
        db.execute("INSERT INTO managed_position VALUES (" + ",".join(["?"]*23) + ")", (
            pid, symbol, "AUDIT_SHADOW", "CLOSED", run, UTC, first,
            "broker-" + first, "FILLED", qty, entry_avg, "0",
            entries, 4, exit_id, "broker-"+exit_id, "FILLED", exit_avg,
            "MAX_HOLD", None, 1, UTC, UTC
        ))
        return first, exit_id

    def order(cid, oid, symbol, side, qty, px, *,
              status="SUBMITTED", context=None, fee_currency="USD", valid=True):
        db.execute("INSERT INTO order_guard VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (cid, UTC, "2026-10-14", symbol, side, 10000, status, oid,
                    None, telemetry(oid, qty, px, context=context,
                                    fee_currency=fee_currency, valid=valid)))

    # 39 single-entry CLOSED positions, with one missing fee-currency case.
    for i in range(39):
        sym = f"S{i:03d}"
        pid = f"pos-shadow-{i:03d}"
        run = f"run-shadow-{i:03d}"
        entry_id, exit_id = position(pid, sym, run, "0.1", "100", "101")
        fee_ccy = None if i == 0 else "USD"
        order(entry_id, "broker-"+entry_id, sym, "BUY", "0.1", "100",
              context=make_context(pid, sym, run, "INITIAL", 0),
              fee_currency=fee_ccy, valid=(i != 2))
        order(exit_id, "broker-"+exit_id, sym, "SELL", "0.1", "101",
              fee_currency=fee_ccy)

    # A multi-entry CLOSED position: the initial order must *not* be
    # projected with the aggregate (0.049034) order quantity.
    sym, pid, run = "LRCX", "pos-lrcx-audit", "run-lrcx-initial"
    entry_id, exit_id = position(pid, sym, run, "0.049034",
                                 "295.9079954725292654", "290.91", entries=2)
    order(entry_id, "broker-"+entry_id, sym, "BUY", "0.025357", "292.61",
          context=make_context(pid, sym, run, "INITIAL", 0))
    addon_run = "run-lrcx-addon"
    addon_id = _expected_client_id(addon_run, sym)
    order(addon_id, "broker-"+addon_id, sym, "BUY", "0.023677", "299.44",
          context=make_context(pid, sym, addon_run, "ADD_ON", 1))
    order(exit_id, "broker-"+exit_id, sym, "SELL", "0.049034", "290.91")

    # 16 orphan order-guard submissions; 15 have historical FILLED evidence,
    # one does not. None has a trustworthy position_id; no symbol/time guesses.
    for i in range(16):
        sym = "LRCX" if i == 0 else "UNKNOWN"
        order(f"orphan-{i:02d}", f"orphan-broker-{i:02d}", sym, "BUY",
              "0.01", "100", context=None, valid=(i != 15))
    db.commit()
    counts = [db.execute("SELECT COUNT(*) FROM "+name).fetchone()[0]
              for name in ("managed_position", "order_guard")]
    db.close()
    assert counts == [40, 97], counts


@unittest.skipUnless(os.getenv("KALMAN_AUDIT_E2E") == "1",
                     "Ephemeral PostgreSQL CI only")
class ShadowMirrorPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("KALMAN_AUDIT_E2E") != "1":
            return
        # A fixed loopback DSN and audit-scoped test DB; no arbitrary PG URL.
        if os.environ.get("KALMAN_AUDIT_PG_DSN") != DSN:
            raise RuntimeError("Refuse anything except disposable local audit Postgres")
        import psycopg
        cls.psycopg = psycopg
        cls.temp = tempfile.TemporaryDirectory(prefix="kalman-shadow-")
        cls.db_path = Path(cls.temp.name)/"synthetic.sqlite3"
        # Import the deterministic client ID helper, no executor or client IO.
        sys.path.insert(0, str(GATEWAY))
        build_sqlite(cls.db_path)
        cls.con = psycopg.connect(DSN)
        with cls.con.cursor() as cur:
            cur.execute(SCHEMA.read_text(encoding="utf-8"))
            cur.execute(SCHEMA.with_name("captured_live_trade_ledger_view.sql").read_text(encoding="utf-8"))
            cur.execute(SCHEMA.with_name("guarded_live_ledger_candidate.sql").read_text(encoding="utf-8"))
            cur.execute("TRUNCATE TABLE trade_execution, managed_position_mirror")
        cls.con.commit()
        cls.run_mirror()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "con", None) is not None:
            cls.con.close()
        if getattr(cls, "temp", None) is not None:
            cls.temp.cleanup()

    @classmethod
    def run_mirror(cls):
        env = dict(os.environ)
        env.update({
            "DATABASE_URL_WRITER": DSN,
            "TRADING_STATE_DB": str(cls.db_path),
            "KALMAN_ENV_FILE": str(Path(cls.temp.name)/"not_present.env"),
            "AUTO_TRADE_EXECUTION_MODE": "DRY_RUN",
            "AUTO_TRADE_SIGNAL_POLICY": "SHADOW_ONLY",
            "PYTHONPATH": str(GATEWAY),
        })
        p = subprocess.run(
            [sys.executable, str(GATEWAY/"engine"/"trade_mirror.py")],
            cwd=str(GATEWAY), env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
            check=False,
        )
        if p.returncode != 0:
            # Never echo environment, secrets or real payloads: test is synthetic.
            raise AssertionError("Synthetic trade_mirror process failed: "+p.stderr[-3500:])
        cls.con.commit()

    def one(self, sql, params=()):
        with self.con.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur.fetchone()

    def test_full_97_event_replay(self):
        self.assertEqual(self.one("SELECT count(*) FROM managed_position_mirror")[0], 40)
        self.assertEqual(self.one("SELECT count(*) FROM trade_execution")[0], 97)
        self.assertEqual(self.one("SELECT count(*) FROM trade_execution WHERE status='FILLED'")[0], 96)
        self.assertEqual(self.one("SELECT count(*) FROM trade_execution WHERE status='SUBMITTED'")[0], 1)

    def test_lrcx_per_order_quantities_not_duplicated(self):
        rows=self.one("""
          SELECT count(*),sum(filled_quantity)
          FROM trade_execution WHERE symbol='LRCX'
            AND position_id='pos-lrcx-audit' AND side='BUY'
        """)
        self.assertEqual(rows[0], 2)
        self.assertEqual(str(rows[1]), "0.049034")
        quantities=self.one("""
          SELECT array_agg(filled_quantity ORDER BY filled_quantity)
          FROM trade_execution WHERE position_id='pos-lrcx-audit' AND side='BUY'
        """)[0]
        self.assertEqual([str(q) for q in quantities],["0.023677","0.025357"])
        pos=self.one("SELECT remaining_quantity,entry_filled_quantity FROM managed_position_mirror WHERE position_id='pos-lrcx-audit'")
        self.assertEqual(str(pos[0]),"0")
        self.assertEqual(str(pos[1]),"0.049034")

    def test_add_on_preserves_link_provenance_and_run(self):
        row=self.one("""
          SELECT metadata->>'position_leg',metadata->>'position_link_source',
                 metadata->>'order_fill_source',run_id,
                 filled_quantity,average_filled_price
          FROM trade_execution
          WHERE position_id='pos-lrcx-audit'
            AND metadata->>'position_leg'='ADD_ON'
        """)
        self.assertEqual(row[:4],("ADD_ON","EXPLICIT_SIGNAL_CONTEXT",
                                  "BROKER_ORDER_TELEMETRY","run-lrcx-addon"))
        self.assertEqual(str(row[4]),"0.023677")
        self.assertEqual(str(row[5]),"299.44")

    def test_multientry_pnl_blocked_not_90_percent_gain(self):
        result=self.one("""
          SELECT metadata #>> '{execution_quality,round_trip,quality_status}',
                 metadata #>> '{execution_quality,round_trip,net_return}',
                 metadata #>> '{execution_quality,round_trip,gross_return}'
          FROM managed_position_mirror WHERE position_id='pos-lrcx-audit'
        """)
        self.assertEqual(result[0],"INCOMPLETE_LEG_COVERAGE")
        self.assertIsNone(result[1])
        self.assertLess(float(result[2]),0)

    def test_managed_filled_without_broker_evidence_has_no_order_quantity(self):
        row=self.one("""
          SELECT status,filled_quantity,
                 metadata->>'order_fill_source',
                 metadata->>'status_source'
          FROM trade_execution
          WHERE client_order_id LIKE 'kalman-S002-%' AND side='BUY'
        """)
        self.assertEqual(row[0],"FILLED")
        self.assertIsNone(row[1])
        self.assertEqual(row[2],"UNVERIFIED")
        self.assertEqual(row[3],"managed_position")

    def test_missing_fee_currency_is_not_zero_fee_success(self):
        row=self.one("""
          SELECT metadata #>> '{execution_quality,round_trip,quality_status}',
                 metadata #>> '{execution_quality,round_trip,net_return}'
          FROM managed_position_mirror WHERE position_id='pos-shadow-000'
        """)
        self.assertEqual(row[0],"UNVERIFIED_FEE_CURRENCY")
        self.assertIsNone(row[1])

    def test_hypothetical_fee_currency_fixture_only(self):
        row=self.one("""
          SELECT metadata #>> '{execution_quality,round_trip,quality_status}',
                 metadata #>> '{execution_quality,round_trip,net_return}'
          FROM managed_position_mirror WHERE position_id='pos-shadow-001'
        """)
        self.assertEqual(row[0],"FULL_LEG_COVERAGE")
        self.assertGreater(float(row[1]),0)

    def test_orphans_remain_unlinked_even_with_matching_symbol(self):
        self.assertEqual(self.one("""
          SELECT count(*) FROM trade_execution
          WHERE client_order_id LIKE 'orphan-%' AND position_id IS NOT NULL
        """)[0],0)
        self.assertEqual(self.one("""
          SELECT count(*) FROM trade_execution
          WHERE client_order_id LIKE 'orphan-%'
            AND metadata->>'order_fill_source'='BROKER_ORDER_TELEMETRY'
        """)[0],15)
        self.assertEqual(self.one("""
          SELECT count(*) FROM trade_execution
          WHERE client_order_id='orphan-15' AND filled_quantity IS NULL
            AND status='SUBMITTED'
        """)[0],1)

    def test_real_neon_view_sql_reads_40_positions_with_fraction_returns(self):
        count=self.one("SELECT count(*) FROM v_live_trade_ledger")[0]
        self.assertEqual(count,40)
        row=self.one("""
          SELECT realized_return_pct, net_return
          FROM v_live_trade_ledger WHERE position_id='pos-lrcx-audit'
        """)
        self.assertLess(row[0],0)
        self.assertGreater(row[0],-0.03)
        self.assertIsNone(row[1])

    def test_release_gate_masked_until_independent_manifest_evidence(self):
        self.assertEqual(self.one("""
          SELECT count(*) FROM v_live_trade_ledger_guarded_candidate
          WHERE net_return IS NOT NULL
        """)[0],0)
        self.assertEqual(self.one("""
          SELECT count(*) FROM v_live_trade_ledger
          WHERE net_return IS NOT NULL
        """)[0],37)
        self.assertEqual(self.one("""
          SELECT count(*) FROM v_live_trade_ledger_guarded_candidate
          WHERE net_return_evidence_status='UNVERIFIED'
        """)[0],40)

    def test_disposable_explicit_manifest_allows_one_synthetic_position(self):
        # Attestation below is synthetic ONLY. No production records or migration.
        with self.con.cursor() as cur:
            cur.execute("""
              UPDATE managed_position_mirror
              SET metadata=jsonb_set(metadata,
                '{execution_quality,round_trip,independent_order_manifest_verified}',
                'true'::jsonb, true)
              WHERE position_id='pos-shadow-001'
            """)
            cur.execute("""
              SELECT net_return,net_return_evidence_status
              FROM v_live_trade_ledger_guarded_candidate
              WHERE position_id='pos-shadow-001'
            """)
            row=cur.fetchone()
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1],'LOCAL_PROVENANCE_ATTESTED')
        self.con.rollback()  # Never persist synthetic eligibility evidence.

    def test_legacy_corrupted_net_is_masked_by_candidate_consumer(self):
        # Simulates old 100%+ net-return metadata in shadow DB only.
        with self.con.cursor() as cur:
            cur.execute("""
              UPDATE managed_position_mirror
              SET metadata=jsonb_set(metadata,
                '{execution_quality,round_trip,net_return}',
                '1.98697'::jsonb, true)
              WHERE position_id='pos-lrcx-audit'
            """)
            cur.execute("""
              SELECT net_return FROM v_live_trade_ledger
              WHERE position_id='pos-lrcx-audit'
            """)
            old=cur.fetchone()[0]
            cur.execute("""
              SELECT net_return,net_return_evidence_status
              FROM v_live_trade_ledger_guarded_candidate
              WHERE position_id='pos-lrcx-audit'
            """)
            safe=cur.fetchone()
        self.assertAlmostEqual(float(old),1.98697)
        self.assertIsNone(safe[0])
        self.assertEqual(safe[1],"UNVERIFIED")
        self.con.rollback()

    def test_observed_production_schema_constraints_are_present(self):
        self.assertEqual(self.one("""
          SELECT count(*) FROM pg_constraint
          WHERE conrelid='trade_execution'::regclass
            AND conname IN ('trade_execution_market_check',
                            'trade_execution_side_check',
                            'trade_execution_execution_mode_check',
                            'trade_execution_client_order_id_key',
                            'trade_execution_pkey')
        """)[0],5)
        self.assertEqual(self.one("""
          SELECT count(*) FROM pg_indexes
          WHERE tablename='trade_execution'
            AND indexname IN ('idx_trade_execution_symbol_updated',
                              'idx_trade_execution_position')
        """)[0],2)
        self.assertEqual(self.one("""
          SELECT count(*) FROM information_schema.columns
          WHERE table_name='trade_execution'
            AND column_name='execution_id'
            AND data_type='uuid'
        """)[0],1)

    def test_repeated_mirror_run_is_idempotent(self):
        self.run_mirror()
        self.assertEqual(self.one("SELECT count(*) FROM managed_position_mirror")[0],40)
        self.assertEqual(self.one("SELECT count(*) FROM trade_execution")[0],97)
        self.assertEqual(self.one("""
          SELECT count(*) FROM trade_execution WHERE
            position_id='pos-lrcx-audit' AND side='BUY'
        """)[0],2)

    def test_all_simulated_rows_do_not_use_live_mode(self):
        self.assertEqual(self.one("""
          SELECT count(*) FROM trade_execution
          WHERE execution_mode != 'DRY_RUN' OR signal_policy != 'SHADOW_ONLY'
        """)[0],0)


if __name__ == "__main__":
    unittest.main()
