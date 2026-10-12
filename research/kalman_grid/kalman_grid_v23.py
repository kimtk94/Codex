"""Paper-only close-observation grid driven by Decimal Ledger V2.2.
No broker, network, LIVE, or intrabar execution assumptions.
"""
import argparse,csv,json,sys
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'kalman_grid_v22'))
from order_ledger import Ledger,State,D

class Grid:
    def __init__(self,anchor, spacing='0.14',levels=100,cash='30000',notional='10000',fee='0.04',exposure_cap='30000'):
        self.anchor=D(anchor);self.spacing=D(spacing)/100;self.levels=int(levels);self.notional=D(notional)
        if self.anchor<=0 or not 0<self.spacing<D('0.5') or self.levels<2 or self.notional<=0:raise ValueError('config')
        self.ledger=Ledger(cash,fee_pct=fee,exposure_cap=exposure_cap)
        self.buy_levels=list(range(-1,-(self.levels+1)//2-1,-1)); self.buys={}; self.sells={};self.fills=[];self.high=D(cash);self.mdd=D(0)
        self._fund()
    def price(self,k):return self.anchor*((1+self.spacing)**k)
    def _fund(self):
        for k in self.buy_levels:
            if k in self.buys or any(x['level']==k for x in self.sells.values()):continue
            p=self.price(k);q=self.notional/p
            try: oid=self.ledger.place('BUY',p,q);self.buys[k]=oid
            except ValueError:break
    def update(self,price,timestamp=''):
        price=D(price)
        if price<=0:raise ValueError('price')
        # Snapshot active orders BEFORE observations. Created orders cannot fill retroactively.
        active_buys=list(self.buys.items()); active_sells=list(self.sells.items())
        for k,oid in active_buys:
            if price<=self.price(k):
                order=self.ledger.orders[oid];qty=order.remaining
                self.ledger.fill(oid,qty)
                del self.buys[k]
                lotid=next(lid for lid in self.ledger.lots if lid.startswith(oid+':'))
                soid=self.ledger.place('SELL',self.price(k+1),qty,parent_id=oid)
                self.sells[soid]={'level':k,'lot_id':lotid}
                self.fills.append({'time':timestamp,'side':'BUY','price':str(order.price),'qty':str(qty),'order_id':oid})
        for soid,info in active_sells:
            order=self.ledger.orders[soid]
            if price>=order.price:
                qty=order.remaining
                self.ledger.fill(soid,qty,lot_id=info['lot_id'])
                del self.sells[soid]
                self.fills.append({'time':timestamp,'side':'SELL','price':str(order.price),'qty':str(qty),'order_id':soid})
        self._fund();self.ledger.audit()
        equity=self.ledger.cash+self.ledger.asset*price
        self.high=max(self.high,equity)
        self.mdd=max(self.mdd,(self.high-equity)/self.high)
    def summary(self,price):
        s=self.ledger.snapshot(price)
        s.update({'return_pct':str((D(s['equity'])/self.ledger.initial-1)*100),'mdd_pct':str(self.mdd*100),'fills':len(self.fills),'active_buys':len(self.buys),'active_sells':len(self.sells),'spacing_pct':str(self.spacing*100),'levels':self.levels,'caveat':'Close-observation model; no intrabar chronology, depth, partial fill or tick-size simulation.'})
        return s

def simulate(rows,**config):
    it=iter(rows); first=next(it); g=Grid(first[1],**config); last=D(first[1]);count=1
    for t,px in it:g.update(px,t);last=D(px);count+=1
    return g,last,count

def main():
    p=argparse.ArgumentParser();p.add_argument('csv_file');p.add_argument('--time-column',default='timestamp');p.add_argument('--price-column',default='close');p.add_argument('--spacing',default='0.14');p.add_argument('--levels',type=int,default=100);p.add_argument('--cash',default='30000');p.add_argument('--notional',default='10000');p.add_argument('--fee',default='0.04');p.add_argument('--exposure-cap',default='30000');p.add_argument('--out');a=p.parse_args()
    with open(a.csv_file,newline='',encoding='utf-8-sig') as f:
        rows=((r[a.time_column],r[a.price_column]) for r in csv.DictReader(f));g,last,count=simulate(rows,spacing=a.spacing,levels=a.levels,cash=a.cash,notional=a.notional,fee=a.fee,exposure_cap=a.exposure_cap)
    report={'bars':count,'summary':g.summary(last),'fills':g.fills}
    if a.out:Path(a.out).write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'bars':count,'summary':report['summary']},indent=2))
if __name__=='__main__':main()
