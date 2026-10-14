"""Synthetic only: fill prices from a sample scenario; fees are HYPOTHETICAL."""
import copy
import unittest
from decimal import Decimal
from multileg_cashflow import reconstruct


def scenario():
    position = {
        "position_id": "pos-synthetic", "symbol": "LRCX", "currency": "USD",
        "state": "CLOSED", "entry_filled_quantity": "0.049034",
        "exit_filled_quantity": "0.049034", "remaining_quantity": "0",
        "entry_average_price": "295.9079954725292654",
        "exit_average_price": "290.91",
    }
    values = [
        ("BUY", "0.025357", "292.61", "2026-10-14T00:39:19+09:00", "initial"),
        ("BUY", "0.023677", "299.44", "2026-10-14T01:39:16+09:00", "add"),
        ("SELL", "0.049034", "290.91", "2026-10-14T22:30:05+09:00", "exit"),
    ]
    events = [{
        "position_id": "pos-synthetic", "symbol": "LRCX",
        "link_basis": "EXIT_CLIENT_ORDER_ID" if side=="SELL" else (
            "ENTRY_CLIENT_ORDER_ID" if label=="initial" else "EXPLICIT_ORDER_POSITION_ID"),
        "broker_order_id": label,
        "reported_broker_order_id": label, "broker_status": "FILLED", "http_status": 200,
        "side": side, "quantity": qty, "price": price, "filled_at": when,
        "currency": "USD", "fee_currency": "USD",
        "commission": "0.01", "tax": "0",
    } for side, qty, price, when, label in values]
    return position, events


class MultilegTests(unittest.TestCase):
    def check(self, p=None, e=None, complete=True, manifest=None):
        pp, ee=scenario()
        manifest_ids=["initial", "add", "exit"] if manifest is None else manifest
        return reconstruct(pp if p is None else p, ee if e is None else e,
                           inventory_complete=complete,
                           expected_broker_order_ids=manifest_ids)

    def test_two_buys_one_sell_cashflows(self):
        out=self.check()
        self.assertEqual(out["status"], "RECONSTRUCTED_HISTORICAL_CASHFLOW")
        self.assertEqual(out["buy_orders"], 2)
        self.assertEqual(out["sell_orders"], 1)
        self.assertEqual(out["buy_quantity"], "0.049034")
        self.assertEqual(out["sell_quantity"], "0.049034")
        self.assertFalse(out["current_broker_balance_verified"])
        self.assertEqual(Decimal(out["gross_pnl"]), Decimal("-0.24507171"))
        self.assertEqual(Decimal(out["net_pnl"]), Decimal("-0.27507171"))
        self.assertLess(Decimal(out["net_return_pct"]), -1.6)

    def test_hypothetical_fees_not_actual(self):
        p,e=scenario()
        for v in e: v["commission"]="0"
        no_fee=reconstruct(p,e,inventory_complete=True,
                           expected_broker_order_ids=["initial","add","exit"])
        with_fee=self.check()
        self.assertLess(Decimal(with_fee["net_pnl"]),Decimal(no_fee["net_pnl"]))

    def test_complete_inventory_is_mandatory(self):
        self.assertEqual(self.check(complete=False)["reason"],"INCOMPLETE_EVENT_INVENTORY")

    def test_missing_addon_blocks_reconstruction(self):
        p,e=scenario()
        e.pop(1)
        self.assertEqual(self.check(p,e)["reason"],"ORDER_MANIFEST_MISMATCH")

    def test_manifest_absent_fails_even_when_quantities_match(self):
        p,e=scenario()
        out=reconstruct(p,e,inventory_complete=True)
        self.assertEqual(out["reason"],"INDEPENDENT_ORDER_MANIFEST_MISSING")

    def test_manifest_duplicate_order_ids_block(self):
        self.assertEqual(self.check(manifest=["initial","add","add"])["reason"],
                         "INVALID_ORDER_MANIFEST")

    def test_manifest_extra_order_blocks(self):
        self.assertEqual(self.check(manifest=["initial","add","exit","unknown"])["reason"],
                         "ORDER_MANIFEST_MISMATCH")

    def test_missing_tax_field_blocks(self):
        p,e=scenario()
        del e[1]["tax"]
        self.assertEqual(self.check(p,e)["reason"],"MISSING_OR_INVALID_FILL_OR_FEES")

    def test_missing_commission_field_blocks(self):
        p,e=scenario()
        del e[1]["commission"]
        self.assertEqual(self.check(p,e)["reason"],"MISSING_OR_INVALID_FILL_OR_FEES")

    def test_duplicate_broker_order_id_blocks(self):
        p,e=scenario()
        e[1]["broker_order_id"]=e[0]["broker_order_id"]
        e[1]["reported_broker_order_id"]=e[0]["broker_order_id"]
        self.assertEqual(self.check(p,e)["reason"],"DUPLICATE_OR_MISSING_BROKER_ORDER_ID")

    def test_symbol_time_is_not_link_proof(self):
        p,e=scenario()
        e[1]["link_basis"]="SYMBOL_AND_TIMESTAMP"
        self.assertEqual(self.check(p,e)["reason"],"UNVERIFIED_POSITION_LINK")

    def test_order_id_not_confirmed(self):
        p,e=scenario()
        e[1]["reported_broker_order_id"]="other"
        self.assertEqual(self.check(p,e)["reason"],"UNCONFIRMED_BROKER_FILL")

    def test_http_failure(self):
        p,e=scenario()
        e[1]["http_status"]=401
        self.assertEqual(self.check(p,e)["reason"],"UNCONFIRMED_HTTP_RESPONSE")

    def test_broker_status_failure(self):
        p,e=scenario()
        e[1]["broker_status"]="SUBMITTED"
        self.assertEqual(self.check(p,e)["reason"],"UNCONFIRMED_BROKER_FILL")

    def test_wrong_currency_blocks(self):
        p,e=scenario()
        e[1]["fee_currency"]="KRW"
        self.assertEqual(self.check(p,e)["reason"],"UNVERIFIED_FEE_CURRENCY")

    def test_negative_fee_blocks(self):
        p,e=scenario()
        e[1]["commission"]="-0.01"
        self.assertEqual(self.check(p,e)["reason"],"MISSING_OR_INVALID_FILL_OR_FEES")

    def test_nan_or_float_quantity_blocks(self):
        for q in ["NaN","Infinity",-1,0,0.023677]:
            with self.subTest(q=q):
                p,e=scenario()
                e[1]["quantity"]=q
                self.assertEqual(self.check(p,e)["reason"],"MISSING_OR_INVALID_FILL_OR_FEES")

    def test_naive_timestamp_blocks(self):
        p,e=scenario()
        e[1]["filled_at"]="2026-10-14T01:39:16"
        self.assertEqual(self.check(p,e)["reason"],"INVALID_FILL_TIMESTAMP")

    def test_sell_before_buy_blocks(self):
        p,e=scenario()
        e[2]["filled_at"]="2026-10-13T22:30:05+09:00"
        self.assertEqual(self.check(p,e)["reason"],"SELL_EXCEEDS_AVAILABLE_SHARES")

    def test_incomplete_close_blocks(self):
        p,e=scenario()
        p["remaining_quantity"]="0.01"
        self.assertEqual(self.check(p,e)["reason"],"POSITION_NOT_FULLY_CLOSED")

    def test_price_mismatch_blocks(self):
        p,e=scenario()
        e[1]["price"]="399.44"
        self.assertEqual(self.check(p,e)["reason"],"WEIGHTED_PRICE_MISMATCH")

    def test_duplicate_execution_prevents_double_count(self):
        p,e=scenario()
        e.append(copy.deepcopy(e[2]))
        self.assertEqual(self.check(p,e)["reason"],"DUPLICATE_OR_MISSING_BROKER_ORDER_ID")

    def test_repeated_pure_evaluation_idempotent(self):
        p,e=scenario()
        original=copy.deepcopy((p,e))
        self.assertEqual(self.check(p,e),self.check(p,e))
        self.assertEqual((p,e),original)

    def test_unrelated_position_link_blocks(self):
        p,e=scenario()
        e[1]["position_id"]="pos-other"
        self.assertEqual(self.check(p,e)["reason"],"UNMATCHED_POSITION")

    def test_partial_fill_zero_status_not_promoted(self):
        p,e=scenario()
        e[1]["broker_status"]="PARTIAL_FILLED"
        self.assertEqual(self.check(p,e)["reason"],"UNCONFIRMED_BROKER_FILL")

    def test_exit_amount_cannot_exceed_entry(self):
        p,e=scenario()
        e[2]["quantity"]="0.059034"
        self.assertEqual(self.check(p,e)["reason"],"SELL_EXCEEDS_AVAILABLE_SHARES")


if __name__=="__main__":
    unittest.main()
