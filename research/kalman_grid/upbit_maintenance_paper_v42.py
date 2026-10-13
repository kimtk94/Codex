"""Maintenance-aware PAPER Grid: exactly one Upbit July 2026 event.

No network/orders. Pauses trading across the observed outage and applies
official reference-price order cancellation at restart before filling.
"""
from upbit_paper_grid_v35 import UpbitPaperGrid
from upbit_maintenance_v42 import stamp,classify_gap,premaintenance_cancel
from kalman_grid_v23 import D

def run_maintenance_aware(rows,market,*,spacing="1.00",fee="0.05",cash="30000",notional="10000",anchor_every=0):
    it=iter(rows)
    first=next(it)
    g=UpbitPaperGrid(first[1],spacing=spacing,fee=fee,cash=cash,notional=notional,exposure_cap=cash)
    prev_time,prev_price=first
    last_price=D(prev_price);count=1
    maintenance_events=[];shifts=0
    for ts,price in it:
        event=classify_gap(prev_time,ts,market)
        if event:
            # Orders were resting until maintenance, not blanket-cancelled.
            reference=D(prev_price)
            cancelled=[]
            for oid in list(g.ledger.active_ids):
                order=g.ledger.orders[oid]
                if premaintenance_cancel(order.side,order.price,reference):
                    g.ledger.cancel(oid)
                    cancelled.append(oid)
                    if order.side=="BUY":
                        for k,key in list(g.buys.items()):
                            if key==oid:del g.buys[k]
                    else:
                        g.sells.pop(oid,None)
            # After exchange resumes, use the first observed post-maintenance
            # price as a MARK ONLY; do not invent a limit fill across the outage.
            # Do not replenish canceled buys until the following observed bar.
            mark=D(price)
            equity=g.ledger.cash+g.ledger.asset*mark
            g.high=max(g.high,equity)
            g.mdd=max(g.mdd,(g.high-equity)/g.high)
            g.ledger.audit()
            maintenance_events.append({"event":event,"before":prev_time,"after":ts,
                                       "pre_maintenance_reference":str(reference),
                                       "cancelled_order_ids":cancelled,"restart_fill_blocked":True})
        else:
            if anchor_every and count % anchor_every==0:
                g.recenter(price);shifts+=1
            g.update(price,ts)
        prev_time,prev_price=ts,price
        last_price=D(price);count+=1
    g.ledger.audit()
    summary=g.summary(last_price)
    return {"market":market,"bars":count,"return_pct":float(summary["return_pct"]),
            "mdd_pct":float(summary["mdd_pct"]),"fills":summary["fills"],
            "fees":float(summary["fees"]),"equity":float(summary["equity"]),
            "recenter_count":shifts,"maintenance_events":maintenance_events,
            "model":"PAPER_MAINTENANCE_AWARE_CLOSE_ONLY"}
