"""PAPER ONLY: explicit side-specific KRW price gate; not a broker adapter."""
from decimal import Decimal
from upbit_krw_rules_v33 import snap_price, validate_order
D=Decimal

def paper_limit_order(side, raw_price, quantity):
    """Snap by explicit BUY/SELL side, then validate notional and quantity.
    Funding must be rechecked by the simulated ledger after snapping.
    """
    side=side.upper()
    price=snap_price(raw_price,side)
    record=validate_order(side,price,quantity)
    record["raw_price"]=str(raw_price)
    record["rounding_delta_krw"]=str(price-D(str(raw_price)))
    record["paper_only"]=True
    return record

def roundtrip_at_ticks(buy_raw,sell_raw,quantity,fee_pct="0.05",slippage_pct="0"):
    """Hypothetical fill-both-legs sensitivity calculation, not a fill simulator."""
    buy=paper_limit_order("BUY",buy_raw,quantity)
    sell=paper_limit_order("SELL",sell_raw,quantity)
    qty=D(str(quantity));bp=D(buy["price"]);sp=D(sell["price"])
    fr=D(str(fee_pct))/100;sr=D(str(slippage_pct))/100
    entry_cost=bp*qty*(1+fr+sr)
    exit_proceeds=sp*qty*(1-fr-sr)
    return {"buy":buy,"sell":sell,"entry_cost_krw":str(entry_cost),
            "exit_proceeds_krw":str(exit_proceeds),
            "net_profit_krw":str(exit_proceeds-entry_cost),
            "net_pct_of_entry":str((exit_proceeds/entry_cost-1)*100),
            "execution_model":"HYPOTHETICAL_BOTH_LIMITS_FILL"}
