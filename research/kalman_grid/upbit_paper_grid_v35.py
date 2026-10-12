"""Upbit KRW PAPER grid with side-aware executable tick prices.

No network/broker/order APIs. Close-only fills are hypothetical.
Standalone subclass: leaves the existing V2.5/V2.6 research engine unchanged.
"""
from decimal import Decimal, ROUND_DOWN
from kalman_grid_v23 import D
from v25_research import RollingGrid
from upbit_grid_contract_v34 import paper_limit_order
from upbit_krw_rules_v33 import snap_price,MIN_ORDER_KRW

class UpbitPaperGrid(RollingGrid):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.ledger.min_notional=MIN_ORDER_KRW
    def limit(self,level,side):
        return snap_price(self.price(level),side)
    def _fund(self):
        # Called by base constructor before this subclass constructor returns.
        for k in self.buy_levels:
            if k in self.buys or any(v["level"]==k for v in self.sells.values()):
                continue
            price=self.limit(k,"BUY")
            qty=(self.notional/price).quantize(D("0.000000000001"),rounding=ROUND_DOWN)
            try:
                paper_limit_order("BUY",price,qty)
                oid=self.ledger.place("BUY",price,qty)
                self.buys[k]=oid
            except ValueError:
                break
    def update(self,price,timestamp=""):
        mark=D(price)
        if mark<=0:raise ValueError("bad market price")
        buys=list(self.buys.items());sells=list(self.sells.items())
        for level,oid in buys:
            order=self.ledger.orders[oid]
            if mark<=order.price:
                qty=order.remaining
                target=self.limit(level+1,"SELL")
                # A SELL with no positive economic margin is not a viable grid.
                # Do not buy and leave an uncovered lot.
                if target<=order.price:continue
                # Full fee reserve and min notional are checked by ledger.
                self.ledger.fill(oid,qty)
                del self.buys[level]
                lot_id=next(k for k in self.ledger.lots if k.startswith(oid+":"))
                paper_limit_order("SELL",target,qty)
                sell_id=self.ledger.place("SELL",target,qty,parent_id=oid)
                self.sells[sell_id]={"level":level,"lot_id":lot_id}
                self.fills.append({"time":timestamp,"side":"BUY","price":str(order.price),"qty":str(qty),"order_id":oid})
        for sid,info in sells:
            order=self.ledger.orders[sid]
            if mark>=order.price:
                qty=order.remaining
                self.ledger.fill(sid,qty,lot_id=info["lot_id"])
                del self.sells[sid]
                self.fills.append({"time":timestamp,"side":"SELL","price":str(order.price),"qty":str(qty),"order_id":sid})
        self._fund()
        self.ledger.audit_fast()
        eq=self.ledger.cash+self.ledger.asset*mark
        self.high=max(self.high,eq)
        self.mdd=max(self.mdd,(self.high-eq)/self.high)

def evaluate_upbit(rows,*,spacing="0.14",anchor_every=0,fee="0.05",slippage="0",cash="30000",notional="10000"):
    """Slip is a conservative haircut of marked-to-market equity, not a fill simulator.
    For realistic fill slippage an execution-aware ledger is required.
    """
    if D(slippage)!=0:raise NotImplementedError("slippage must be modeled in fills, not approximated as P&L haircut")
    it=iter(rows);ts,p=next(it)
    grid=UpbitPaperGrid(p,spacing=spacing,levels=100,cash=cash,notional=notional,fee=fee,exposure_cap=cash)
    count=1;shifts=0
    for ts,p in it:
        if anchor_every and count%anchor_every==0:
            grid.recenter(p);shifts+=1
        grid.update(p,ts);count+=1
    grid.ledger.audit()
    summary=grid.summary(p)
    return {"bars":count,"return_pct":float(summary["return_pct"]),"mdd_pct":float(summary["mdd_pct"]),
        "fees":float(summary["fees"]),"fills":summary["fills"],"shifts":shifts,
        "final_equity":float(summary["equity"]),"active_lots":len(grid.ledger.lots),
        "status":"PAPER_CLOSE_ONLY_NO_SLIPPAGE"}
