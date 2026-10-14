"""Deterministic model-based cash-flow stress, not a historical backtest.

No live data or IO; randomized quantities/prices/fees with independently
calculated Decimal oracle and deliberate corruption checks.
"""
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from random import Random
import unittest
from multileg_cashflow import reconstruct


def make_case(seed):
    r=Random(seed)
    n=r.randint(1,4)
    position_id="stress-pos-"+str(seed)
    symbol="S"+str(seed)
    base=datetime(2026,10,14,12,0,tzinfo=timezone.utc)
    orders=[]
    qtys=[]
    for i in range(n):
        qty=Decimal(r.randint(1,300))/Decimal("10000")
        price=Decimal(r.randint(3000,120000))/100
        qtys.append(qty)
        orders.append(("BUY",qty,price))
    total=sum(qtys)
    exit_price=Decimal(r.randint(3000,120000))/100
    orders.append(("SELL",total,exit_price))
    event_rows=[]
    manifest=[]
    amounts={"BUY":Decimal(0),"SELL":Decimal(0)}
    fees={"BUY":Decimal(0),"SELL":Decimal(0)}
    for index,(side,qty,price) in enumerate(orders):
        commission=Decimal(r.randint(0,3))/1000
        tax=Decimal(r.randint(0,2))/1000
        oid="mock-"+str(seed)+"-"+str(index)
        manifest.append(oid)
        amounts[side]+=qty*price
        fees[side]+=commission+tax
        event_rows.append({
            "position_id":position_id,"symbol":symbol,
            "link_basis":"ENTRY_CLIENT_ORDER_ID" if index==0 else (
                "EXIT_CLIENT_ORDER_ID" if side=="SELL" else "EXPLICIT_ORDER_POSITION_ID"),
            "broker_order_id":oid,"reported_broker_order_id":oid,
            "broker_status":"FILLED","http_status":200,
            "side":side,"quantity":str(qty),"price":str(price),
            "filled_at":(base+timedelta(minutes=index)).isoformat(),
            "currency":"USD","fee_currency":"USD",
            "commission":str(commission),"tax":str(tax),
        })
    position={
        "position_id":position_id,"symbol":symbol,"currency":"USD","state":"CLOSED",
        "entry_filled_quantity":str(total),"exit_filled_quantity":str(total),
        "remaining_quantity":"0",
        "entry_average_price":str(amounts["BUY"]/total),
        "exit_average_price":str(exit_price),
    }
    pnl=amounts["SELL"]-amounts["BUY"]-fees["BUY"]-fees["SELL"]
    pct=pnl/(amounts["BUY"]+fees["BUY"])*100
    return position,event_rows,manifest,pnl,pct


class ModelBasedStress(unittest.TestCase):
    def test_1000_order_sequenced_cashflows_against_decimal_oracle(self):
        for seed in range(1000):
            with self.subTest(seed=seed):
                p,events,manifest,pnl,pct=make_case(310000+seed)
                out=reconstruct(p,events,inventory_complete=True,
                                expected_broker_order_ids=manifest,
                                price_tolerance="0.000001")
                self.assertEqual(out["status"],"RECONSTRUCTED_HISTORICAL_CASHFLOW")
                self.assertEqual(Decimal(out["net_pnl"]),pnl)
                self.assertEqual(Decimal(out["net_return_pct"]),pct)
                self.assertEqual(out["buy_orders"],len(events)-1)
                self.assertEqual(out["sell_orders"],1)

    def test_500_corrupted_inventories_all_fail_closed(self):
        for seed in range(500):
            p,events,manifest,_,_=make_case(920000+seed)
            with self.subTest(seed=seed,mutation="unlisted"):
                shortened=events[:-1]
                out=reconstruct(p,shortened,inventory_complete=True,
                                expected_broker_order_ids=manifest)
                self.assertEqual(out["status"],"UNVERIFIED")
            with self.subTest(seed=seed,mutation="unlinked"):
                corrupted=copy.deepcopy(events)
                corrupted[0]["link_basis"]="SYMBOL_AND_TIME"
                out=reconstruct(p,corrupted,inventory_complete=True,
                                expected_broker_order_ids=manifest)
                self.assertEqual(out["reason"],"UNVERIFIED_POSITION_LINK")
            with self.subTest(seed=seed,mutation="missing_fee"):
                corrupted=copy.deepcopy(events)
                del corrupted[-1]["tax"]
                out=reconstruct(p,corrupted,inventory_complete=True,
                                expected_broker_order_ids=manifest)
                self.assertEqual(out["reason"],"MISSING_OR_INVALID_FILL_OR_FEES")
            with self.subTest(seed=seed,mutation="duplicated"):
                corrupted=events+[copy.deepcopy(events[-1])]
                out=reconstruct(p,corrupted,inventory_complete=True,
                                expected_broker_order_ids=manifest)
                self.assertEqual(out["status"],"UNVERIFIED")


if __name__=="__main__":
    unittest.main()
