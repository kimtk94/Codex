"""Regression checks for explicit future ADD_ON linkage to mirror rows.

All observations are synthetic. These tests never open a DB or broker API.
"""
import ast
from copy import deepcopy
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalman-toss-gateway"))
from engine.order_position_link import explicit_buy_link, _expected_client_id
from engine.broker_status_evidence import historical_broker_fill


class ExplicitMirrorLinkTests(unittest.TestCase):
    def setUp(self):
        self.pos = {
            "position_id": "pos-initial", "symbol": "LRCX",
            "strategy_version": "R5.1_TEST", "entry_run_id": "run-first",
            "entry_count": 2, "entry_client_order_id": _expected_client_id("run-first", "LRCX"),
        }
        self.context = {
            "managed_position_id": self.pos["position_id"], "symbol": "LRCX",
            "strategy_version": "R5.1_TEST", "run_id": "run-second",
            "entry_type": "ADD_ON", "entry_count_before": 1,
            "signal_as_of": "2026-10-14T01:39:00+09:00",
        }
        self.order = {
            "symbol": "LRCX", "side": "BUY",
            "client_order_id": _expected_client_id("run-second", "LRCX"),
            "toss_order_id": "broker-demo", "status": "SUBMITTED",
        }
        self.telemetry = {
            "signal_context": self.context,
            "broker_order": {
                "order_id": "broker-demo", "status": "FILLED",
                "filled_quantity": "0.023677", "average_filled_price": "299.44",
                "filled_at": "2026-10-14T01:39:16+09:00",
                "response_meta": {"status_code": 200},
            },
        }

    def check(self, order=None, telemetry=None, positions=None):
        return explicit_buy_link(self.order if order is None else order,
                                 self.telemetry if telemetry is None else telemetry,
                                 [self.pos] if positions is None else positions)

    def test_add_on_links_explicitly_without_broker_assertion(self):
        result = self.check()
        self.assertEqual(result["status"], "EXPLICIT_LOCAL_LINK")
        self.assertEqual(result["leg"], "ADD_ON")
        self.assertEqual(result["position_id"], "pos-initial")
        self.assertFalse(result["broker_confirmed"])

    def test_historical_broker_fill_is_separate_proof(self):
        self.assertIsNotNone(historical_broker_fill(self.order, self.telemetry))

    def test_same_symbol_timestamp_without_pid_cannot_link(self):
        x=deepcopy(self.telemetry)
        del x["signal_context"]["managed_position_id"]
        self.assertEqual(self.check(telemetry=x)["reason"], "EXPLICIT_POSITION_ID_MISSING")

    def test_client_id_must_match_run_and_symbol(self):
        x={**self.order, "client_order_id":"other-order"}
        self.assertEqual(self.check(order=x)["reason"], "CLIENT_ORDER_ID_MISMATCH")

    def test_context_run_id_is_required(self):
        x=deepcopy(self.telemetry)
        x["signal_context"]["run_id"]=""
        self.assertEqual(self.check(telemetry=x)["reason"], "RUN_ID_MISSING")

    def test_context_symbol_mismatch(self):
        x=deepcopy(self.telemetry)
        x["signal_context"]["symbol"]="AMD"
        self.assertEqual(self.check(telemetry=x)["reason"], "SYMBOL_MISMATCH")

    def test_duplicate_position_ids_rejected(self):
        self.assertEqual(self.check(positions=[self.pos,self.pos])["reason"],
                         "POSITION_NOT_UNIQUE")

    def test_position_strategy_mismatch_rejected(self):
        x=deepcopy(self.telemetry)
        x["signal_context"]["strategy_version"]="INCOMPATIBLE"
        self.assertEqual(self.check(telemetry=x)["reason"], "STRATEGY_VERSION_MISMATCH")

    def test_unverified_ordinal_fails(self):
        x=deepcopy(self.telemetry)
        x["signal_context"]["entry_count_before"]=10
        self.assertEqual(self.check(telemetry=x)["reason"], "INVALID_ADD_ON_ORDINAL")

    def test_true_boolean_ordinal_fails(self):
        x=deepcopy(self.telemetry)
        x["signal_context"]["entry_count_before"]=True
        self.assertEqual(self.check(telemetry=x)["reason"], "INVALID_ADD_ON_ORDINAL")

    def test_initial_link_requires_entry_client_id(self):
        x=deepcopy(self.telemetry)
        x["signal_context"].update({"entry_type":"INITIAL", "run_id":"run-first",
                                    "entry_count_before":0})
        order={**self.order,"client_order_id":_expected_client_id("run-first","LRCX")}
        self.assertEqual(self.check(order=order,telemetry=x)["leg"],"INITIAL")

    def test_only_buy_orders(self):
        self.assertEqual(self.check(order={**self.order,"side":"SELL"})["reason"],"UNSUPPORTED_SIDE")

    def test_no_input_mutation(self):
        before=deepcopy((self.pos,self.order,self.telemetry))
        self.check()
        self.assertEqual((self.pos,self.order,self.telemetry),before)

    def test_mirror_main_source_integrates_verified_link_and_add_on_run(self):
        source=(ROOT/"kalman-toss-gateway"/"engine"/"trade_mirror.py").read_text()
        tree=ast.parse(source)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)
               and isinstance(n.func,ast.Name) and n.func.id=="explicit_buy_link"]
        self.assertEqual(len(calls),1)
        self.assertIn('position_link_source = "EXPLICIT_SIGNAL_CONTEXT"',source)
        self.assertIn('signal_context.get("run_id") if leg == "ADD_ON"',source)
        self.assertIn('"position_link_source": position_link_source',source)
        self.assertIn('pos.get("position_id") if pos else None',source)

    def test_no_historical_relink_without_tag(self):
        legacy={"signal_context": {"entry_type":"ADD_ON", "run_id":"run-second",
            "symbol":"LRCX", "strategy_version":"R5.1_TEST",
            "entry_count_before":1}}
        self.assertEqual(self.check(telemetry=legacy)["status"],"UNKNOWN")


if __name__=="__main__":
    unittest.main()
