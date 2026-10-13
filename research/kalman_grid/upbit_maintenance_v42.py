"""Upbit July 2026 maintenance event: research-only schedule and order policy.

Upbit notice: https://docs.upbit.com/kr/v1.6.4/changelog/server_maintenance_0706
KST 2026-07-06 02:00 maintenance; staged restart 06:40.
Observed BTC/ETH 1-minute outage 2026-07-05 17:01 UTC..21:50 UTC.
"""
from datetime import datetime, timezone
from decimal import Decimal
START=datetime.fromisoformat("2026-07-05T17:00:00+00:00")
FIRST_POST_BAR=datetime.fromisoformat("2026-07-05T21:51:00+00:00")
LAST_PRE_BAR=datetime.fromisoformat("2026-07-05T17:00:00+00:00")
SOURCE="https://docs.upbit.com/kr/v1.6.4/changelog/server_maintenance_0706"

def stamp(value):
    t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None:t=t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)

def classify_gap(left,right,market):
    """Return event identifier only for the EXACT evidenced exchange outage."""
    a,b=stamp(left),stamp(right)
    if market in ("KRW-BTC","KRW-ETH") and a==LAST_PRE_BAR and b==FIRST_POST_BAR:
        return "EXCHANGE_MAINTENANCE_20260706"
    return None

def premaintenance_cancel(order_side,order_price,last_trade_price):
    """According to Upbit notice, buy > reference and sell < reference canceled.
    Equal-price orders remain; resting valid orders are not blanket-canceled.
    """
    p=Decimal(str(order_price));ref=Decimal(str(last_trade_price))
    if p<=0 or ref<=0:raise ValueError("invalid prices")
    side=order_side.upper()
    if side=="BUY":return p>ref
    if side=="SELL":return p<ref
    raise ValueError("invalid side")

def gap_audit(csv_path, market):
    import csv
    with open(csv_path,newline="") as f:items=list(csv.DictReader(f))
    intervals=[]; missing=0;approved_missing=0;nonmaintenance_max=1
    for left,right in zip(items,items[1:]):
        a,b=stamp(left["t"]),stamp(right["t"])
        delta=int((b-a).total_seconds()/60)
        if delta<=0:raise ValueError("invalid order / duplicate timestamps")
        if delta==1:continue
        event=classify_gap(left["t"],right["t"],market)
        count=delta-1
        intervals.append({"before":left["t"],"after":right["t"],"missing":count,"event":event})
        missing+=count
        if event:approved_missing+=count
        else:nonmaintenance_max=max(nonmaintenance_max,delta)
    return {"market":market,"rows":len(items),"missing_minutes":missing,
            "approved_maintenance_missing_minutes":approved_missing,
            "residual_missing_minutes":missing-approved_missing,
            "max_nonmaintenance_gap_minutes":nonmaintenance_max,"intervals":intervals}
