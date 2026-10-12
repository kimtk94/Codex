"""Deterministic Decimal paper-only order ledger. No brokerage/network connections."""
from dataclasses import dataclass
from decimal import Decimal, getcontext
from enum import Enum
getcontext().prec = 34
D = lambda x: Decimal(str(x))
class State(str, Enum):
    NEW='NEW'; OPEN='OPEN'; PARTIAL='PARTIAL'; FILLED='FILLED'; CANCELLED='CANCELLED'; REJECTED='REJECTED'
TERMINAL={State.FILLED, State.CANCELLED, State.REJECTED}
@dataclass
class Order:
    id: str
    side: str
    price: Decimal
    quantity: Decimal
    state: State
    filled: Decimal=D(0)
    reserved: Decimal=D(0)
    proceeds: Decimal=D(0)
    cost_basis: Decimal=D(0)
    parent_id: str|None=None
    @property
    def remaining(self): return self.quantity-self.filled
class Ledger:
    def __init__(self, cash, fee_pct='0.04', min_qty='0.00000001', min_notional='0', exposure_cap=None):
        self.initial=D(cash); self.cash=D(cash); self.asset=D(0); self.fees=D(0)
        self.fee=D(fee_pct)/100; self.min_qty=D(min_qty); self.min_notional=D(min_notional)
        self.exposure_cap=D(exposure_cap) if exposure_cap is not None else None
        self.orders={}; self.lots={}; self.events=[]; self.realized=D(0); self._seq=0
        if self.cash<0 or self.fee<0 or self.fee>=1 or self.min_qty<=0: raise ValueError('bad configuration')
    def _id(self): self._seq+=1; return f'P{self._seq:08d}'
    @property
    def locked(self): return sum((o.reserved for o in self.orders.values()), D(0))
    @property
    def free(self): return self.cash-self.locked
    @property
    def sell_locked(self): return sum((o.remaining for o in self.orders.values() if o.side=='SELL' and o.state not in TERMINAL),D(0))
    def place(self,side,price,qty,parent_id=None):
        side=side.upper(); price=D(price); qty=D(qty)
        if side not in ('BUY','SELL') or price<=0 or qty<self.min_qty or price*qty<self.min_notional: raise ValueError('invalid order')
        if parent_id is not None and parent_id not in self.orders: raise ValueError('unknown parent')
        locked = price*qty*(1+self.fee) if side=='BUY' else D(0)
        if side=='BUY' and locked>self.free: raise ValueError('insufficient free cash')
        if side=='SELL' and qty>self.asset-self.sell_locked: raise ValueError('insufficient available inventory')
        if side=='BUY' and self.exposure_cap is not None:
            inventory_limit=sum((lot['qty']*lot['buy_price'] for lot in self.lots.values()),D(0))
            reserved_buy=sum((o.price*o.remaining for o in self.orders.values() if o.side=='BUY' and o.state not in TERMINAL),D(0))
            if inventory_limit+reserved_buy+price*qty>self.exposure_cap: raise ValueError('exposure cap')
        oid=self._id(); self.orders[oid]=Order(oid,side,price,qty,State.OPEN,reserved=locked,parent_id=parent_id)
        self.events.append(('PLACE',oid,side,str(price),str(qty))); self.audit(); return oid
    def fill(self,oid,qty,execution_price=None,lot_id=None):
        o=self.orders[oid]; qty=D(qty); px=o.price if execution_price is None else D(execution_price)
        if o.state in TERMINAL or qty<=0 or qty>o.remaining or px<=0: raise ValueError('invalid fill')
        if (o.side=='BUY' and px>o.price) or (o.side=='SELL' and px<o.price): raise ValueError('limit violation')
        fee=qty*px*self.fee
        if o.side=='BUY':
            spend=qty*px+fee
            release=o.price*qty*(1+self.fee)
            if spend>release: raise AssertionError('budget underreserved')
            self.cash-=spend; self.asset+=qty; o.reserved-=release
            lotkey=f'{oid}:{len([x for x in self.lots if x.startswith(oid+":")])+1}'
            self.lots[lotkey]={'qty':qty,'cost':spend,'buy_price':px,'order_id':oid}
        else:
            if lot_id is None: raise ValueError('sell fill requires explicit lot_id')
            lot=self.lots.get(lot_id)
            if lot is None or lot['qty']<qty: raise ValueError('insufficient lot quantity')
            basis=lot['cost']*qty/lot['qty']; lot['qty']-=qty;lot['cost']-=basis
            if lot['qty']==0: del self.lots[lot_id]
            self.asset-=qty; self.cash+=qty*px-fee; self.realized+=qty*px-fee-basis
            o.proceeds+=qty*px-fee; o.cost_basis+=basis
        o.filled+=qty; self.fees+=fee; o.state=State.FILLED if o.remaining==0 else State.PARTIAL
        self.events.append(('FILL',oid,str(qty),str(px),str(fee),lot_id))
        self.audit();return o.state
    def cancel(self,oid):
        o=self.orders[oid]
        if o.state in TERMINAL: raise ValueError('order already final')
        o.reserved=D(0);o.state=State.CANCELLED;self.events.append(('CANCEL',oid));self.audit()
    def replace(self,oid,new_price,new_qty):
        o=self.orders[oid]
        if o.state in TERMINAL: raise ValueError('order already final')
        new_qty=D(new_qty)
        if new_qty<=0: raise ValueError('bad replacement quantity')
        side=o.side;parent=o.parent_id
        self.cancel(oid)
        return self.place(side,new_price,new_qty,parent)
    def audit(self):
        assert self.cash>=0 and self.free>=0 and self.asset>=0
        assert self.sell_locked<=self.asset
        assert sum((x['qty'] for x in self.lots.values()),D(0))==self.asset
        for o in self.orders.values():
            assert 0<=o.filled<=o.quantity
            if o.side=='BUY':
                should = o.price*o.remaining*(1+self.fee) if o.state not in TERMINAL else D(0)
                assert o.reserved==should,(o.id,o.reserved,should)
            else: assert o.reserved==0
            if o.state==State.FILLED: assert o.remaining==0
            if o.state==State.PARTIAL: assert 0<o.filled<o.quantity
        assert self.initial+self.realized==self.cash+self.inventory_cost()
        return True
    def inventory_cost(self): return sum((x['cost'] for x in self.lots.values()),D(0))
    def snapshot(self,market_price):
        px=D(market_price)
        if px<=0: raise ValueError('invalid market price')
        equity=self.cash+self.asset*px
        return {'mode':'PAPER_ONLY','cash':str(self.cash),'free':str(self.free),'locked':str(self.locked),'asset':str(self.asset),'equity':str(equity),'realized_pnl':str(self.realized),'unrealized_pnl':str(self.asset*px-self.inventory_cost()),'fees':str(self.fees),'orders':len(self.orders)}
