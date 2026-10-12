"""Upbit KRW spot order validation. PAPER/RESEARCH ONLY, no API orders.

2025-07-31+ KRW price tick table from Upbit docs; verify market-specific
exceptions and current policy before any real-world order use.
"""
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING

PRICE_STEPS = (
    ("1000000","1000"),("500000","500"),("100000","100"),
    ("50000","50"),("10000","10"),("5000","5"),("1000","1"),
    ("100","1"),("10","0.1"),("1","0.01"),("0.1","0.001"),
    ("0.01","0.0001"),("0.001","0.00001"),("0.0001","0.000001"),
    ("0.00001","0.0000001"),("0","0.00000001"),
)
D=Decimal
MIN_ORDER_KRW=D("5000")
def price_tick(price):
    p=D(str(price))
    if p<=0:raise ValueError("non-positive price")
    for floor,step in PRICE_STEPS:
        if p>=D(floor):return D(step)
    raise AssertionError("unreachable")
def snap_price(price,side):
    """Conservative limit rounding: BUY down, SELL up.

    Re-evaluate at price-tier boundary. Does NOT imply any fill.
    """
    p=D(str(price));side=side.upper()
    if side not in ("BUY","SELL"):raise ValueError("side")
    for _ in range(3):
        step=price_tick(p)
        q=(p/step).to_integral_value(rounding=ROUND_FLOOR if side=="BUY" else ROUND_CEILING)*step
        if price_tick(q)==step:return q
        p=q
    raise ValueError("tier boundary needs policy review")
def validate_order(side,price,quantity):
    p=D(str(price));qty=D(str(quantity))
    if qty<=0 or p<=0:raise ValueError("non-positive order")
    if p!=snap_price(p,side):raise ValueError("off-tick order price")
    notional=p*qty
    if notional<MIN_ORDER_KRW:raise ValueError("below 5000 KRW minimum")
    return {"side":side.upper(),"price":str(p),"quantity":str(qty),"notional_krw":str(notional)}
def roundtrip_margin(spacing_pct,fee_pct_each_side,slippage_pct_each_side="0"):
    """Approximate percentage-point margin; excludes spread & non-linear compounding."""
    return D(str(spacing_pct))-2*(D(str(fee_pct_each_side))+D(str(slippage_pct_each_side)))
